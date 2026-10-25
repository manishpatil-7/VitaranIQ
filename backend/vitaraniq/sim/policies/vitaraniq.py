"""
Full VitaranIQ Policy: Quantile Forecasts + Newsvendor Targets + CP-SAT Optimizer.
Implements FR-SIM-04.
"""

from typing import Any, Dict, List, Tuple
import pandas as pd

from vitaraniq.check.checks import check_plan
from vitaraniq.db.snapshot import Snapshot
from vitaraniq.explain.reason_codes import explain_and_format_plan_lines
from vitaraniq.forecast.predict import predict_quantiles
from vitaraniq.forecast.train import ForecastModelBundle
from vitaraniq.optimize.fefo_repair import apply_fefo_repair
from vitaraniq.optimize.model import build_and_solve_cpsat
from vitaraniq.service_level.newsvendor import make_targets


class PolicyVitaranIQ:
    name: str = "VITARANIQ"

    def __init__(
        self,
        model: ForecastModelBundle,
        sales_df: pd.DataFrame,
        calendar_df: pd.DataFrame,
        stores_df: pd.DataFrame,
        products_df: pd.DataFrame,
    ):
        self.model = model
        self.sales_df = sales_df
        self.calendar_df = calendar_df
        self.stores_df = stores_df
        self.products_df = products_df

    def plan(self, snapshot: Snapshot, day: int) -> List[Dict[str, Any]]:
        as_of = day
        truck_cap_ml = 4000000

        # 1. Forecast quantiles
        forecast_table = predict_quantiles(
            model=self.model,
            sales_df=self.sales_df,
            calendar_df=self.calendar_df,
            stores_df=self.stores_df,
            products_df=self.products_df,
            as_of_day=as_of,
        )

        # 2. Service level mapping -> Targets
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
        )

        # 3. Solve CP-SAT integer program in deterministic mode
        raw_plan = build_and_solve_cpsat(
            snapshot=snapshot,
            targets=targets,
            time_limit_s=8.0,
            deterministic=True,
            workers=1,
        )

        # 4. FEFO repair
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
            store_onhand=store_onhand,
        )
        raw_plan.shipments = repaired

        # 5. Format and explain lines
        formatted_lines = explain_and_format_plan_lines(
            snapshot=snapshot,
            targets=targets,
            raw_plan=raw_plan,
            as_of_day=as_of,
            truck_cap_ml=truck_cap_ml,
        )

        # 6. Check plan
        check_res = check_plan(snapshot, formatted_lines, targets, truck_cap_ml)
        check_res.raise_if_failed()

        return formatted_lines
