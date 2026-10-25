"""
Plan Service for VitaranIQ.
Orchestrates end-to-end plan generation:
Snapshot -> Forecast -> Targets -> CP-SAT Solve -> FEFO Repair -> Explain -> Check -> Persist.
Maintains <= 15s latency budget with per-stage timing breakdown.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import sqlite3

from vitaraniq.check.checks import check_plan
from vitaraniq.core.config import load_params
from vitaraniq.core.ids import generate_plan_id, utc_now_iso
from vitaraniq.core.timers import StageTimer
from vitaraniq.db.session import get_db_path, get_sqlite_connection
from vitaraniq.db.snapshot import Snapshot, load_snapshot_from_db
from vitaraniq.explain.reason_codes import explain_and_format_plan_lines
from vitaraniq.optimize.fefo_repair import apply_fefo_repair
from vitaraniq.optimize.model import RawPlan, build_and_solve_cpsat
from vitaraniq.service_level.newsvendor import Targets, make_targets
from vitaraniq.services.forecast_svc import ForecastService


class PlanService:
    @classmethod
    def generate_plan(
        cls,
        dataset_id: str,
        as_of_day: int = 703,
        supply_scenario: str = "normal",
        scenario_type: str = "NONE",
        scenario_params: Optional[Dict[str, Any]] = None,
        base_plan_id: Optional[str] = None,
        time_limit_s: float = 8.0,
        deterministic: bool = False,
        workers: int = 4,
        db_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Generate, verify, explain, and store an optimal weekly dispatch plan."""
        timer = StageTimer()
        params = load_params()
        plan_id = generate_plan_id()
        unavailable_warehouses = []
        if scenario_type == "WAREHOUSE_OUTAGE" and scenario_params:
            unavail_wh = scenario_params.get("warehouse_id")
            if unavail_wh:
                unavailable_warehouses.append(unavail_wh)

        conn = get_sqlite_connection(db_path)
        try:
            # Stage 1: Load Snapshot
            with timer.stage("load_snapshot"):
                snapshot = load_snapshot_from_db(dataset_id=dataset_id, as_of_day=as_of_day, conn=conn)

            # Stage 2: Forecast Inference
            with timer.stage("forecast_inference"):
                model_version = ForecastService.get_active_model_version(conn)
                if not model_version:
                    raise ValueError("No active forecast model found. Train model first.")
                forecast_table = ForecastService.predict_for_day(
                    dataset_id=dataset_id,
                    as_of_day=as_of_day,
                    model_version=model_version,
                    conn=conn,
                )

            # Stage 3: Service-Level Mapping -> Targets
            with timer.stage("service_level_targets"):
                store_onhand = {
                    (st_id, sku_id): stock["qty"]
                    for (st_id, sku_id), stock in snapshot.store_onhand.items()
                }
                intransit = {
                    (it["store_id"], it["sku_id"]): it["qty"]
                    for it in snapshot.intransit
                }
                targets = make_targets(
                    forecast_table=forecast_table,
                    store_onhand=store_onhand,
                    intransit=intransit,
                    params=params,
                )

            # Stage 4: CP-SAT Optimization
            with timer.stage("cpsat_solve"):
                raw_plan = build_and_solve_cpsat(
                    snapshot=snapshot,
                    targets=targets,
                    params=params,
                    time_limit_s=time_limit_s,
                    deterministic=deterministic,
                    workers=workers,
                    unavailable_warehouses=unavailable_warehouses,
                )

            # Stage 5: Deterministic FEFO Repair
            with timer.stage("fefo_repair"):
                batch_stock = {b["batch_id"]: b["qty"] for b in snapshot.batches}
                lane_transit = {k: v.get("transit_days", 1) for k, v in snapshot.lanes.items()}
                sku_min_life = {p["sku_id"]: p["min_life_days"] for p in snapshot.products}
                repaired_shipments = apply_fefo_repair(
                    raw_shipments=raw_plan.shipments,
                    batches_stock=batch_stock,
                    all_batches=snapshot.batches,
                    lanes_transit=lane_transit,
                    sku_min_life=sku_min_life,
                    as_of_day=as_of_day,
                    targets=targets,
                    store_onhand=store_onhand,
                )
                raw_plan.shipments = repaired_shipments

            # Stage 6: Explainability & Cost Allocation
            with timer.stage("explainability"):
                formatted_lines = explain_and_format_plan_lines(
                    snapshot=snapshot,
                    targets=targets,
                    raw_plan=raw_plan,
                    as_of_day=as_of_day,
                    truck_cap_ml=params.network.trucks.capacity_ml,
                )

            # Stage 7: Independent Plan-Checker Validation
            with timer.stage("plan_checker"):
                check_result = check_plan(
                    snapshot=snapshot,
                    lines=formatted_lines,
                    targets=targets,
                    truck_cap_ml=params.network.trucks.capacity_ml,
                )
                check_result.raise_if_failed()

            # Stage 8: Database Persistence
            with timer.stage("db_persist"):
                cur = conn.cursor()
                cur.execute("BEGIN TRANSACTION;")

                # Aggregate plan header metrics
                tot_unmet_units = sum(raw_plan.unmet_demand.values())
                cur.execute("""
                    INSERT INTO plans (
                        plan_id, dataset_id, model_version, as_of_day,
                        supply_scenario, scenario_type, scenario_params_json,
                        base_plan_id, solver_status, gap_pct, solve_time_s,
                        solver_workers, deterministic, checker_status,
                        n_lines, total_cost_paise, transport_paise,
                        unmet_units, stage_timings_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    plan_id, dataset_id, model_version, as_of_day,
                    supply_scenario, scenario_type,
                    json.dumps(scenario_params) if scenario_params else None,
                    base_plan_id, raw_plan.status, raw_plan.gap_pct, raw_plan.solve_time_s,
                    workers, 1 if deterministic else 0, check_result.status,
                    len(formatted_lines), raw_plan.total_cost_paise, raw_plan.transport_paise,
                    tot_unmet_units, json.dumps(timer.timings), utc_now_iso()
                ))

                # Insert plan_lines and plan_line_reasons
                for line in formatted_lines:
                    cur.execute("""
                        INSERT INTO plan_lines (
                            plan_id, line_no, sku_id, warehouse_id, store_id,
                            batch_id, batch_expiry_day, qty, trucks_on_lane,
                            line_cost_paise, priority
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        plan_id, line["line_no"], line["sku_id"], line["warehouse_id"],
                        line["store_id"], line["batch_id"], line["batch_expiry_day"],
                        line["qty"], line["trucks_on_lane"], line["line_cost_paise"],
                        line["priority"]
                    ))

                    for r in line["reason_codes"]:
                        cur.execute("""
                            INSERT INTO plan_line_reasons (plan_id, line_no, code, evidence_json)
                            VALUES (?, ?, ?, ?)
                        """, (
                            plan_id, line["line_no"], r["code"], json.dumps(r["evidence"])
                        ))

                # Insert plan_targets
                for (s_id, sku_id), t_obj in targets.store_sku_targets.items():
                    cur.execute("""
                        INSERT INTO plan_targets (
                            plan_id, store_id, sku_id, p50, p70, p80, p90,
                            critical_ratio, chosen_quantile, target_q, onhand,
                            intransit, cold_start
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        plan_id, s_id, sku_id, t_obj.p50_9d, t_obj.p70_9d, t_obj.p80_9d, t_obj.p90_9d,
                        t_obj.critical_ratio, t_obj.chosen_quantile, t_obj.target_q,
                        t_obj.onhand, t_obj.intransit, t_obj.cold_start
                    ))

                # Insert plan_unmet
                for (s_id, sku_id), u_val in raw_plan.unmet_demand.items():
                    if u_val > 0:
                        p_info = snapshot.prod_map[sku_id]
                        m_risk = u_val * p_info["margin_paise"]
                        cur.execute("""
                            INSERT INTO plan_unmet (plan_id, store_id, sku_id, units, margin_at_risk_paise)
                            VALUES (?, ?, ?, ?, ?)
                        """, (plan_id, s_id, sku_id, u_val, m_risk))

                conn.commit()

            return {
                "plan_id": plan_id,
                "as_of_day": as_of_day,
                "model_version": model_version,
                "solver": {
                    "status": raw_plan.status,
                    "gap_pct": raw_plan.gap_pct,
                    "solve_time_s": raw_plan.solve_time_s,
                    "workers": workers,
                },
                "checker": {
                    "status": check_result.status,
                    "violations": len(check_result.violations),
                },
                "stage_timings": timer.timings,
                "kpis": {
                    "total_cost_inr": round(raw_plan.total_cost_paise / 100.0, 2),
                    "transport_inr": round(raw_plan.transport_paise / 100.0, 2),
                    "lost_sales_inr": round(raw_plan.lost_sales_paise / 100.0, 2),
                    "wastage_inr": round(raw_plan.wastage_paise / 100.0, 2),
                    "unmet_units": tot_unmet_units,
                    "n_lines": len(formatted_lines),
                },
                "lines": formatted_lines,
            }
        finally:
            conn.close()
