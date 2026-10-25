"""
Policy O-MA: Optimizer driven by 7-day Moving Average forecast.
Implements FR-SIM-04 and AIML Design §9.2.
Isolates the AI forecasting contribution over the optimization algorithm alone.
"""

from typing import Any, Dict, List, Tuple
import math

from vitaraniq.check.checks import check_plan
from vitaraniq.db.snapshot import Snapshot
from vitaraniq.explain.reason_codes import explain_and_format_plan_lines
from vitaraniq.optimize.fefo_repair import apply_fefo_repair
from vitaraniq.optimize.model import build_and_solve_cpsat
from vitaraniq.service_level.newsvendor import StoreSkuTarget, Targets


class PolicyOMA:
    name: str = "O_MA"

    def __init__(self, daily_sales_ma7: Dict[Tuple[str, str], float]):
        """daily_sales_ma7: (store_id, sku_id) -> mean daily sales of last 7 days."""
        self.ma7 = daily_sales_ma7

    def plan(self, snapshot: Snapshot, day: int) -> List[Dict[str, Any]]:
        as_of = day
        truck_cap_ml = 4000000

        # Build flat targets from 7-day moving average
        targets_dict = {}
        for s in snapshot.stores:
            s_id = s["store_id"]
            for p in snapshot.products:
                sku_id = p["sku_id"]
                ma = self.ma7.get((s_id, sku_id), p["base_units_per_day"] * s["size_mult"])
                p50_val = int(round(9.0 * ma))
                target_val = int(math.ceil(1.25 * 9.0 * ma))

                onhand = snapshot.store_onhand.get((s_id, sku_id), {}).get("qty", 0)
                intransit = sum(
                    it["qty"] for it in snapshot.intransit if it["store_id"] == s_id and it["sku_id"] == sku_id
                )

                targets_dict[(s_id, sku_id)] = StoreSkuTarget(
                    store_id=s_id,
                    sku_id=sku_id,
                    p50_9d=p50_val,
                    p70_9d=target_val,
                    p80_9d=target_val,
                    p90_9d=target_val,
                    critical_ratio=0.80,
                    chosen_quantile=0.80,
                    target_q=target_val,
                    onhand=onhand,
                    intransit=intransit,
                )

        targets = Targets(store_sku_targets=targets_dict)

        # Solve CP-SAT integer program in deterministic mode
        raw_plan = build_and_solve_cpsat(
            snapshot=snapshot,
            targets=targets,
            time_limit_s=8.0,
            deterministic=True,
            workers=1,
        )

        # FEFO repair
        batch_stock = {b["batch_id"]: b["qty"] for b in snapshot.batches}
        lane_transit = {k: v.get("transit_days", 1) for k, v in snapshot.lanes.items()}
        sku_min_life = {p["sku_id"]: p["min_life_days"] for p in snapshot.products}
        repaired = apply_fefo_repair(
            raw_shipments=raw_plan.shipments,
            batches_stock=batch_stock,
            all_batches=snapshot.batches,
            lanes_transit=lane_transit,
            sku_min_life=sku_min_life,
            as_of_day=as_of,
            targets=targets,
            store_onhand={k: v["qty"] for k, v in snapshot.store_onhand.items()},
        )
        raw_plan.shipments = repaired

        # Format and explain lines
        formatted_lines = explain_and_format_plan_lines(
            snapshot=snapshot,
            targets=targets,
            raw_plan=raw_plan,
            as_of_day=as_of,
            truck_cap_ml=truck_cap_ml,
        )

        # Check plan
        check_res = check_plan(snapshot, formatted_lines, targets, truck_cap_ml)
        check_res.raise_if_failed()

        return formatted_lines
