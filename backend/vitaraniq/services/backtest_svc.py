"""
Backtest Orchestration Service.
Implements FR-SIM-01 through FR-SIM-09, conforming to System Architecture §5 and Database Schema §5.
Runs simulations for policies across demand seeds and supply scenarios, persisting to database.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path

from vitaraniq.core.ids import generate_run_id, utc_now_iso
from vitaraniq.db.session import get_db_path, get_sqlite_connection
from vitaraniq.sim.engine import SimEngine
from vitaraniq.sim.policies.b1 import PolicyB1
from vitaraniq.sim.policies.b2 import PolicyB2
from vitaraniq.sim.policies.o_ma import PolicyOMA
from vitaraniq.sim.policies.vitaraniq import PolicyVitaranIQ
from vitaraniq.sim.kpis import compute_ablation_summary


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BacktestService:
    @classmethod
    def run_backtest(
        cls,
        dataset_id: str,
        seeds: Optional[List[int]] = None,
        scenarios: Optional[List[str]] = None,
        policies: Optional[List[str]] = None,
        model_version: Optional[str] = None,
        db_path: Optional[Path] = None,
        truck_cap_ml: int = 4000000,
    ) -> Dict[str, Any]:
        """
        Execute full backtest matrix (policies x seeds x scenarios).
        Default: 4 policies x 5 seeds {11,12,13,14,15} x 2 scenarios {normal, scarcity}.
        """
        if seeds is None:
            seeds = [11, 12, 13, 14, 15]
        if scenarios is None:
            scenarios = ["normal", "scarcity"]
        if policies is None:
            policies = ["B1", "B2", "O_MA", "VITARANIQ"]

        run_id = generate_run_id()
        conn = get_sqlite_connection(db_path)
        conn.row_factory = sqlite3.Row

        try:
            cur = conn.cursor()

            # Resolve model_version
            if model_version is None:
                cur.execute("SELECT model_version FROM models WHERE dataset_id = ? ORDER BY trained_at DESC LIMIT 1", (dataset_id,))
                r = cur.fetchone()
                if r:
                    model_version = r[0]
                else:
                    cur.execute("SELECT model_version FROM models ORDER BY trained_at DESC LIMIT 1")
                    r = cur.fetchone()
                    model_version = r[0] if r else "m_lightgbm_v1"
                    cur.execute("""
                        INSERT OR IGNORE INTO models (
                            model_version, dataset_id, trained_at, seed,
                            feature_list_json, params_json, lib_versions_json,
                            artifact_path, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'READY')
                    """, (
                        model_version, dataset_id, utc_now_iso(), 42,
                        "[]", "{}", "{}", "models/lightgbm_default"
                    ))


            cur.execute("""
                INSERT INTO backtest_runs (
                    run_id, dataset_id, model_version, status, seeds_json, scenarios_json, policies_json, created_at
                ) VALUES (?, ?, ?, 'RUNNING', ?, ?, ?, ?)
            """, (
                run_id, dataset_id, model_version, json.dumps(seeds), json.dumps(scenarios),
                json.dumps(policies), utc_now_iso()
            ))
            conn.commit()


            # Pre-compute historical sales statistics from sales_daily
            # m28: mean daily sales days 675 to 702
            cur.execute("""
                SELECT store_id, sku_id, AVG(units) AS m28
                FROM sales_daily
                WHERE dataset_id = ? AND day BETWEEN 675 AND 702
                GROUP BY store_id, sku_id
            """, (dataset_id,))
            m28_map = {(r["store_id"], r["sku_id"]): float(r["m28"]) for r in cur.fetchall()}

            # m7: mean daily sales days 696 to 702
            cur.execute("""
                SELECT store_id, sku_id, AVG(units) AS m7
                FROM sales_daily
                WHERE dataset_id = ? AND day BETWEEN 696 AND 702
                GROUP BY store_id, sku_id
            """, (dataset_id,))
            m7_map = {(r["store_id"], r["sku_id"]): float(r["m7"]) for r in cur.fetchall()}


            # Policy factory
            policy_instances = {}
            if "B1" in policies:
                policy_instances["B1"] = PolicyB1(sales_history_means=m28_map, buffer_factor=1.0)
            if "B2" in policies:
                policy_instances["B2"] = PolicyB2(sales_history_means=m28_map)

            if "O_MA" in policies:
                policy_instances["O_MA"] = PolicyOMA(means_7d=m7_map)
            if "VITARANIQ" in policies:
                policy_instances["VITARANIQ"] = PolicyVitaranIQ(dataset_id=dataset_id, db_path=db_path)

            all_sim_results = []

            # Execute simulation matrix
            for scn in scenarios:
                for s in seeds:
                    for pol_name in policies:
                        pol = policy_instances[pol_name]
                        engine = SimEngine(
                            dataset_id=dataset_id,
                            seed=s,
                            supply_scenario=scn,
                            policy=pol,
                            conn=conn,
                            truck_cap_ml=truck_cap_ml,
                        )
                        res = engine.run(run_id=run_id)
                        all_sim_results.append(res)

                        # Insert into sim_results
                        cur.execute("""
                            INSERT INTO sim_results (
                                run_id, policy, seed, supply_scenario,
                                units_demanded, units_sold, units_unmet, units_delivered,
                                store_days_total, store_days_stockout,
                                wastage_units, wastage_paise, transport_paise,
                                trips, loaded_ml, truck_capacity_ml_total,
                                lost_margin_paise, margin_demanded_paise, margin_sold_paise
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            run_id, res["policy"], res["seed"], res["supply_scenario"],
                            res["units_demanded"], res["units_sold"], res["units_unmet"], res["units_delivered"],
                            res["store_days_total"], res["store_days_stockout"],
                            res["wastage_units"], res["wastage_paise"], res["transport_paise"],
                            res["trips"], res["loaded_ml"], res["truck_capacity_ml_total"],
                            res["lost_margin_paise"], res["margin_demanded_paise"], res["margin_sold_paise"]
                        ))

                        # Insert into sim_daily
                        for d_rec in res["daily_records"]:
                            cur.execute("""
                                INSERT INTO sim_daily (
                                    run_id, policy, seed, supply_scenario, day,
                                    units_demanded, units_sold, units_unmet,
                                    wastage_paise, transport_paise
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                run_id, d_rec["policy"], d_rec["seed"], d_rec["supply_scenario"], d_rec["day"],
                                d_rec["units_demanded"], d_rec["units_sold"], d_rec["units_unmet"],
                                d_rec["wastage_paise"], d_rec["transport_paise"]
                            ))

                        # Insert into sim_plan_checks
                        for c_rec in res["plan_checks_records"]:
                            cur.execute("""
                                INSERT INTO sim_plan_checks (
                                    run_id, policy, seed, supply_scenario, plan_day,
                                    checker_status, n_lines
                                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                run_id, c_rec["policy"], c_rec["seed"], c_rec["supply_scenario"],
                                c_rec["plan_day"], c_rec["checker_status"], c_rec["n_lines"]
                            ))

                        conn.commit()

            # Mark run complete
            cur.execute("""
                UPDATE backtest_runs
                SET status = 'COMPLETE', finished_at = ?
                WHERE run_id = ?
            """, (utc_now_iso(), run_id))
            conn.commit()

            # Compute ablation metrics
            # Add total_cost_paise to sim results for ablation calculation
            for r in all_sim_results:
                r["total_cost_paise"] = r["transport_paise"] + r["lost_margin_paise"] + r["wastage_paise"]
            ablation = compute_ablation_summary(all_sim_results)

            return {
                "run_id": run_id,
                "dataset_id": dataset_id,
                "status": "COMPLETE",
                "seeds": seeds,
                "scenarios": scenarios,
                "policies": policies,
                "n_simulations": len(all_sim_results),
                "ablation": ablation,
            }

        except Exception as e:
            cur.execute("""
                UPDATE backtest_runs
                SET status = 'FAILED', finished_at = ?
                WHERE run_id = ?
            """, (utc_now_iso(), run_id))
            conn.commit()
            raise e
        finally:
            conn.close()

    @classmethod
    def get_run_results(cls, run_id: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
        """Fetch backtest results, KPI view summary, and ablation breakdown."""
        conn = get_sqlite_connection(db_path)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Run header
            cur.execute("SELECT * FROM backtest_runs WHERE run_id = ?", (run_id,))
            run_row = cur.fetchone()
            if not run_row:
                raise ValueError(f"Run {run_id} not found")

            # KPIs from view
            cur.execute("""
                SELECT run_id, policy, seed, supply_scenario,
                       fill_rate, stockout_rate, wastage_paise, transport_paise,
                       cost_per_unit_delivered_paise, truck_fill, total_cost_paise,
                       margin_weighted_fill_rate
                FROM v_sim_kpis
                WHERE run_id = ?
            """, (run_id,))
            kpi_rows = [dict(r) for r in cur.fetchall()]

            # Also fetch detailed totals for aggregation
            cur.execute("SELECT * FROM sim_results WHERE run_id = ?", (run_id,))
            raw_results = [dict(r) for r in cur.fetchall()]
            for r in raw_results:
                r["total_cost_paise"] = r["transport_paise"] + r["lost_margin_paise"] + r["wastage_paise"]

            ablation = compute_ablation_summary(raw_results)

            return {
                "run": dict(run_row),
                "kpis": kpi_rows,
                "ablation": ablation,
            }
        finally:
            conn.close()
