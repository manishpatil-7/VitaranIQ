"""
Inference module for VitaranIQ LightGBM Quantile Forecaster.
Produces 300 store-SKU quantile forecasts in <= 2 seconds.
"""

from typing import Dict, List, Tuple
import numpy as np
import pandas as pd

from vitaraniq.forecast.features import build_feature_matrix_for_origins
from vitaraniq.forecast.train import ForecastModelBundle


def predict_quantiles(
    model: ForecastModelBundle,
    sales_df: pd.DataFrame,
    calendar_df: pd.DataFrame,
    stores_df: pd.DataFrame,
    products_df: pd.DataFrame,
    as_of_day: int,
) -> Dict[Tuple[str, str], Dict[str, int]]:
    """
    Produce calibrated, monotonically sorted integer quantile forecasts
    for all (store_id, sku_id) pairs at origin day as_of_day.
    """
    X, _, scales, meta = build_feature_matrix_for_origins(
        sales_df=sales_df,
        calendar_df=calendar_df,
        stores_df=stores_df,
        products_df=products_df,
        origins=[as_of_day],
        weekday_indices=model.weekday_indices,
        is_training=False,
    )

    preds_raw = {}
    for q in [0.5, 0.7, 0.8, 0.9]:
        booster = model.boosters[q]
        pred_ratio = booster.predict(X)
        c_q = model.calibration_factors.get(q, 1.0)
        preds_raw[q] = pred_ratio * scales * c_q

    # Monotonic post-processing
    stacked = np.stack([preds_raw[0.5], preds_raw[0.7], preds_raw[0.8], preds_raw[0.9]], axis=1)
    stacked = np.sort(stacked, axis=1)
    stacked = np.ceil(np.maximum(stacked, 0.0)).astype(int)

    forecast_table = {}
    for idx, m in enumerate(meta):
        s_id = m["store_id"]
        sku_id = m["sku_id"]
        forecast_table[(s_id, sku_id)] = {
            "p50": int(stacked[idx, 0]),
            "p70": int(stacked[idx, 1]),
            "p80": int(stacked[idx, 2]),
            "p90": int(stacked[idx, 3]),
            "cold_start": 0,
        }

    return forecast_table
