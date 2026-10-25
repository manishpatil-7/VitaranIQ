"""
Forecast Training, Accuracy, and Series Visualizer Routes.
Conforms to System Architecture §6, SRS FR-FCT-01..09, and AIML Design §3.
"""

from typing import Any, Dict, List, Optional
import sqlite3
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from vitaraniq.core.config import load_params
from vitaraniq.db.session import get_sqlite_connection
from vitaraniq.services.forecast_svc import ForecastService
from vitaraniq.service_level.newsvendor import compute_critical_ratio, map_critical_ratio_to_quantile
from vitaraniq.api.schemas import (
    ForecastTrainRequest,
    ForecastTrainResponse,
    ForecastSeriesResponse,
)

router = APIRouter(prefix="/forecast", tags=["Forecast"])



@router.post("/train", response_model=ForecastTrainResponse)
def train_forecast(req: ForecastTrainRequest):
    conn = get_sqlite_connection()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT dataset_id FROM datasets ORDER BY created_at DESC LIMIT 1;")
        row_ds = cur.fetchone()
        if not row_ds:
            raise HTTPException(status_code=404, detail="No dataset found. Generate data first.")
        dataset_id = row_ds["dataset_id"]
    finally:
        conn.close()

    try:
        bundle, metrics = ForecastService.train_and_save(dataset_id=dataset_id, seed=req.seed)
        return ForecastTrainResponse(
            model_version=bundle.model_version,
            dataset_id=dataset_id,
            quantiles=[0.50, 0.70, 0.80, 0.90],
            metrics=metrics,
            training_time_seconds=0.0,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accuracy")
def get_forecast_accuracy():
    conn = get_sqlite_connection()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT model_version FROM models WHERE status = 'READY' ORDER BY trained_at DESC LIMIT 1;")
        row_m = cur.fetchone()
        if not row_m:
            raise HTTPException(status_code=404, detail="No trained model found. Train model first.")
        model_version = row_m["model_version"]

        cur.execute("""
            SELECT scope, scope_id, n_windows, wape_model, wape_ma9, bias,
                   cov_p50, cov_p70, cov_p80, cov_p90, pinball_loss
            FROM forecast_metrics
            WHERE model_version = ?
            ORDER BY scope, scope_id
        """, (model_version,))
        rows = [dict(r) for r in cur.fetchall()]

        return {
            "model_version": model_version,
            "metrics": rows,
        }
    finally:
        conn.close()


@router.get("/series", response_model=ForecastSeriesResponse)
def get_forecast_series(
    store_id: str = Query(..., description="Store ID (e.g. S01)"),
    sku_id: str = Query(..., description="SKU ID (e.g. MILK-500ML)"),
):
    conn = get_sqlite_connection()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check latest dataset and model
        cur.execute("SELECT dataset_id FROM datasets ORDER BY created_at DESC LIMIT 1;")
        row_ds = cur.fetchone()
        if not row_ds:
            raise HTTPException(status_code=404, detail="Dataset not found")
        dataset_id = row_ds["dataset_id"]

        params = load_params()
        p_config = params.get_product(sku_id)
        if not p_config:
            raise HTTPException(status_code=404, detail=f"SKU {sku_id} not found in configuration")

        cr = compute_critical_ratio(p_config, params.optimization.holding_cost_rate)
        ch_q = map_critical_ratio_to_quantile(cr, params.forecasting.service_level_floor)


        # Fetch last 28 days of history (days 675 to 702)
        cur.execute("""
            SELECT s.day, c.date, s.units AS actual
            FROM sales_daily s
            JOIN calendar c ON s.dataset_id = c.dataset_id AND s.day = c.day
            WHERE s.dataset_id = ? AND s.store_id = ? AND s.sku_id = ?
              AND s.day BETWEEN 675 AND 702
            ORDER BY s.day ASC
        """, (dataset_id, store_id, sku_id))
        history_rows = [dict(r) for r in cur.fetchall()]

        # Generate or load 9-day forward forecast
        preds = ForecastService.predict_for_day(dataset_id=dataset_id, as_of_day=703, conn=conn)
        pred_dict = preds.get((store_id, sku_id), {})
        p50 = pred_dict.get("p50", 0)
        p70 = pred_dict.get("p70", 0)
        p80 = pred_dict.get("p80", 0)
        p90 = pred_dict.get("p90", 0)

        # Get calendar dates for days 703 to 711
        cur.execute("""
            SELECT day, date FROM calendar
            WHERE dataset_id = ? AND day BETWEEN 703 AND 711
            ORDER BY day ASC
        """, (dataset_id,))
        cal_map = {r["day"]: r["date"] for r in cur.fetchall()}

        forecast_rows = []
        # Daily distribution (approx 1/9th per day for visualization)
        for d in range(703, 712):
            forecast_rows.append({
                "day": d,
                "date": cal_map.get(d, f"Day {d}"),
                "p50_daily": round(p50 / 9.0, 1),
                "p70_daily": round(p70 / 9.0, 1),
                "p80_daily": round(p80 / 9.0, 1),
                "p90_daily": round(p90 / 9.0, 1),
            })

        q_key = f"p{int(ch_q * 100)}"
        target_q_val = pred_dict.get(q_key, p70)

        return ForecastSeriesResponse(
            store_id=store_id,
            sku_id=sku_id,
            critical_ratio=cr,
            chosen_quantile=f"P{int(ch_q * 100)}",
            target_q=int(target_q_val),
            history=history_rows,
            forecast=forecast_rows,
        )
    finally:
        conn.close()
