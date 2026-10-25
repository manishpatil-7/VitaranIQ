"""
What-If Scenario Service for VitaranIQ.
Implements FR-WIF-01..04 and Architecture §5.4.
Computes impact deltas for warehouse outages, demand spikes, and fuel price shocks.
"""

from typing import Any, Dict, List, Optional
import json
import sqlite3

from vitaraniq.db.session import get_db_path, get_sqlite_connection
from vitaraniq.services.plan_svc import PlanService


class WhatIfService:
    @classmethod
    def run_warehouse_outage(
        cls,
        base_plan_id: str,
        outage_warehouse_id: str,
        dataset_id: Optional[str] = None,
        as_of_day: Optional[int] = None,
        workers: int = 4,
        db_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Simulate outage of a warehouse: sets its stock to 0 and re-plans.
        Returns the re-optimized plan along with a comparative delta table.
        """
        conn = get_sqlite_connection(db_path)
        try:
            cur = conn.cursor()
            # 1. Fetch base plan
            cur.execute("""
                SELECT plan_id, dataset_id, as_of_day, total_cost_paise, transport_paise, unmet_units,
                       stage_timings_json
                FROM plans WHERE plan_id = ?
            """, (base_plan_id,))
            base_row = cur.fetchone()
            if not base_row:
                raise ValueError(f"Base plan {base_plan_id} not found")

            if dataset_id is None:
                dataset_id = base_row[1]
            if as_of_day is None:
                as_of_day = base_row[2]

            base_transport = base_row[4]
            base_unmet = base_row[5]

            # Fetch base plan line counts and store shipments
            cur.execute("SELECT store_id, sku_id, qty FROM plan_lines WHERE plan_id = ?", (base_plan_id,))
            base_lines_map = {(r[0], r[1]): r[2] for r in cur.fetchall()}

            cur.execute("SELECT warehouse_id, store_id, trucks, loaded_ml, truck_cost_paise FROM plan_lanes WHERE plan_id = ?", (base_plan_id,))
            base_lanes = cur.fetchall()
            base_lanes_map = {(r[0], r[1]): {"trucks": r[2], "volume_ml": r[3], "cost_inr": round(r[4] / 100.0, 2)} for r in base_lanes}
            base_trucks = sum(r[2] for r in base_lanes)

            # 2. Run new plan with outage scenario
            outage_plan = PlanService.generate_plan(
                dataset_id=dataset_id,
                as_of_day=as_of_day,
                scenario_type="WAREHOUSE_OUTAGE",
                scenario_params={"warehouse_id": outage_warehouse_id},
                base_plan_id=base_plan_id,
                time_limit_s=8.0,
                deterministic=True,
                workers=workers,
                db_path=db_path,
            )

            new_plan_id = outage_plan["plan_id"]
            new_transport = outage_plan["kpis"]["transport_inr"] * 100  # in paise
            new_unmet = outage_plan["kpis"]["unmet_units"]

            # Compute delta metrics
            delta_transport_paise = int(new_transport - base_transport)
            delta_unmet_units = int(new_unmet - base_unmet)

            # Check affected stores
            new_lines = outage_plan["lines"]
            cur.execute("SELECT warehouse_id, store_id, trucks, loaded_ml, truck_cost_paise FROM plan_lanes WHERE plan_id = ?", (new_plan_id,))
            new_lanes = cur.fetchall()
            new_lanes_map = {(r[0], r[1]): {"trucks": r[2], "volume_ml": r[3], "cost_inr": round(r[4] / 100.0, 2)} for r in new_lanes}
            new_trucks = sum(r[2] for r in new_lanes)
            delta_trucks = new_trucks - base_trucks

            affected_stores = set()
            new_lines_map = {(l["store_id"], l["sku_id"]): l["qty"] for l in new_lines}

            for k in set(base_lines_map.keys()).union(new_lines_map.keys()):
                if base_lines_map.get(k, 0) != new_lines_map.get(k, 0):
                    affected_stores.add(k[0])

            # Displaced stores previously fed by outage_warehouse_id
            outage_stores = [s for (w, s) in base_lanes_map.keys() if w == outage_warehouse_id]
            displaced_stores = []
            for s in sorted(outage_stores):
                new_whs = [w for (w, st) in new_lanes_map.keys() if st == s]
                displaced_stores.append({
                    "store_id": s,
                    "previous_warehouse": outage_warehouse_id,
                    "new_warehouses": new_whs,
                })

            # New routes formed
            new_routes = []
            for (w, s), info in new_lanes_map.items():
                if (w, s) not in base_lanes_map:
                    new_routes.append({
                        "warehouse_id": w,
                        "store_id": s,
                        "trucks": info["trucks"],
                        "volume_ml": info["volume_ml"],
                        "cost_inr": info["cost_inr"],
                    })

            # Insert plan_deltas record
            cur.execute("""
                INSERT INTO plan_deltas (
                    plan_id, base_plan_id, delta_transport_paise, delta_unmet_units,
                    delta_margin_risk_paise, delta_trucks, affected_stores_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                new_plan_id,
                base_plan_id,
                delta_transport_paise,
                delta_unmet_units,
                0,  # delta margin risk
                delta_trucks,
                json.dumps(sorted(list(affected_stores)))
            ))
            conn.commit()

            comparison = {
                "base_plan_id": base_plan_id,
                "whatif_plan_id": new_plan_id,
                "outage_warehouse_id": outage_warehouse_id,
                "delta_transport_paise": delta_transport_paise,
                "delta_transport_inr": round(delta_transport_paise / 100.0, 2),
                "delta_unmet_units": delta_unmet_units,
                "delta_trucks": delta_trucks,
                "base_transport_inr": round(base_transport / 100.0, 2),
                "new_transport_inr": round(new_transport / 100.0, 2),
                "base_unmet_units": base_unmet,
                "new_unmet_units": new_unmet,
                "affected_stores_count": len(affected_stores),
                "affected_stores": sorted(list(affected_stores)),
            }

            return {
                "whatif_plan_id": new_plan_id,
                "base_plan_id": base_plan_id,
                "outage_warehouse_id": outage_warehouse_id,
                "comparison": comparison,
                "displaced_stores": displaced_stores,
                "new_routes": new_routes,
                "delta": comparison,
                "lines": new_lines,
                "kpis": outage_plan["kpis"],
                "plan_id": new_plan_id,
            }
        finally:
            conn.close()
