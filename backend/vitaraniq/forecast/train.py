"""
LightGBM Quantile Forecaster Training Pipeline.
Implements FR-FCT-01..07 and AIML Design §4.4.
Trains 4 quantile boosters (P50, P70, P80, P90) with early stopping on validation segment.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple
import lightgbm as lgb
import numpy as np
import pandas as pd

from vitaraniq.core.config import SystemParams, load_params
from vitaraniq.core.ids import compute_sha256, utc_now_iso
from vitaraniq.forecast.features import (
    FEATURE_NAMES,
    build_feature_matrix_for_origins,
    compute_weekday_indices,
)
from vitaraniq.forecast.metrics import compute_coverage, evaluate_forecasts


class ForecastModelBundle:
    def __init__(
        self,
        model_version: str,
        boosters: Dict[float, lgb.Booster],
        weekday_indices: Dict[int, float],
        calibration_factors: Dict[float, float],
        meta: Dict[str, Any],
        metrics: Dict[str, Any],
    ):
        self.model_version = model_version
        self.boosters = boosters
        self.weekday_indices = weekday_indices
        self.calibration_factors = calibration_factors
        self.meta = meta
        self.metrics = metrics

    def save(self, base_dir: Path):
        model_dir = base_dir / self.model_version
        model_dir.mkdir(parents=True, exist_ok=True)

        for q, booster in self.boosters.items():
            fname = model_dir / f"q{int(q*100)}.txt"
            booster.save_model(str(fname))

        meta_path = model_dir / "meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "model_version": self.model_version,
                "weekday_indices": self.weekday_indices,
                "calibration_factors": self.calibration_factors,
                **self.meta
            }, f, indent=2)

        metrics_path = model_dir / "metrics.json"
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(self.metrics, f, indent=2)

    @classmethod
    def load(cls, model_dir: Path) -> "ForecastModelBundle":
        meta_path = model_dir / "meta.json"
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        metrics_path = model_dir / "metrics.json"
        with open(metrics_path, "r", encoding="utf-8") as f:
            metrics = json.load(f)

        boosters = {}
        for q in [0.5, 0.7, 0.8, 0.9]:
            fname = model_dir / f"q{int(q*100)}.txt"
            boosters[q] = lgb.Booster(model_file=str(fname))

        return cls(
            model_version=meta["model_version"],
            boosters=boosters,
            weekday_indices={int(k): v for k, v in meta["weekday_indices"].items()},
            calibration_factors={float(k): v for k, v in meta["calibration_factors"].items()},
            meta=meta,
            metrics=metrics,
        )


def train_quantile_models(
    sales_df: pd.DataFrame,
    calendar_df: pd.DataFrame,
    stores_df: pd.DataFrame,
    products_df: pd.DataFrame,
    dataset_hash: str,
    seed: int = 42,
    params: SystemParams = None,
) -> ForecastModelBundle:
    """Train 4 LightGBM quantile models following the time-ordered split."""
    if params is None:
        params = load_params()

    # Step 1: Weekday index from training segment only (days <= 620)
    weekday_indices = compute_weekday_indices(sales_df, max_train_day=620)

    # Step 2: Build train, val, test origin lists
    train_origins = list(range(29, 621))
    val_origins = list(range(630, 664))
    test_origins = list(range(673, 722))

    X_train, y_train, scale_train, _ = build_feature_matrix_for_origins(
        sales_df, calendar_df, stores_df, products_df, train_origins, weekday_indices, is_training=True
    )
    X_val, y_val, scale_val, _ = build_feature_matrix_for_origins(
        sales_df, calendar_df, stores_df, products_df, val_origins, weekday_indices, is_training=True
    )
    X_test, y_test, scale_test, meta_test = build_feature_matrix_for_origins(
        sales_df, calendar_df, stores_df, products_df, test_origins, weekday_indices, is_training=True
    )

    quantiles = [0.5, 0.7, 0.8, 0.9]
    boosters = {}
    val_preds = {}
    test_preds = {}

    train_data = lgb.Dataset(X_train, label=y_train, feature_name=FEATURE_NAMES, free_raw_data=False)
    val_data = lgb.Dataset(X_val, label=y_val, feature_name=FEATURE_NAMES, reference=train_data, free_raw_data=False)

    for q in quantiles:
        lgb_params = {
            "objective": "quantile",
            "alpha": q,
            "metric": "quantile",
            "learning_rate": 0.08,
            "num_leaves": 45,
            "min_data_in_leaf": 150,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 1,
            "lambda_l2": 1.0,
            "seed": seed,
            "deterministic": True,
            "force_row_wise": True,
            "verbose": -1,
            "num_threads": 4,
        }

        # Train booster with early stopping on validation segment
        callbacks = [lgb.early_stopping(stopping_rounds=60, verbose=False)]
        booster = lgb.train(
            lgb_params,
            train_data,
            num_boost_round=600,
            valid_sets=[val_data],
            callbacks=callbacks,
        )
        boosters[q] = booster
        val_preds[q] = booster.predict(X_val) * scale_val
        test_preds[q] = booster.predict(X_test) * scale_test

    # Step 3: Check calibration on validation set
    y_val_actual = y_val * scale_val
    calibration_factors = {}
    for q in quantiles:
        emp_cov = compute_coverage(y_val_actual, val_preds[q])
        if abs(emp_cov - q) > 0.03:
            ratio = y_val_actual / np.maximum(val_preds[q], 1.0)
            c_q = float(np.quantile(ratio, q))
            c_q = float(np.clip(c_q, 0.85, 1.20))
        else:
            c_q = 1.0
        calibration_factors[q] = c_q
        # Apply calibration
        test_preds[q] = test_preds[q] * c_q

    # Post-process test predictions: monotonic sort, clip at 0, ceil
    raw_p50 = test_preds[0.5]
    raw_p70 = test_preds[0.7]
    raw_p80 = test_preds[0.8]
    raw_p90 = test_preds[0.9]

    stacked = np.stack([raw_p50, raw_p70, raw_p80, raw_p90], axis=1)
    stacked = np.sort(stacked, axis=1)
    stacked = np.ceil(np.maximum(stacked, 0.0))

    final_test_preds = {
        0.5: stacked[:, 0],
        0.7: stacked[:, 1],
        0.8: stacked[:, 2],
        0.9: stacked[:, 3],
    }

    # Step 4: Baseline MA9 on test origins
    # MA9 = 9 * mean of daily sales over last 7 days (s7 / 7 * 9 = s7 * 9 / 7)
    # Feature 1 is s7_norm = s7 / scale
    # Thus s7 = s7_norm * scale
    s7_vals = X_test[:, 1] * scale_test
    ma9_preds = np.ceil(s7_vals * (9.0 / 7.0))

    y_test_actual = y_test * scale_test
    eval_metrics = evaluate_forecasts(y_test_actual, final_test_preds, ma9_preds)

    # Compute model version string
    ver_hash = compute_sha256(f"{dataset_hash}_{seed}_{json.dumps(FEATURE_NAMES)}")[:8]
    model_version = f"lgbm_q_{ver_hash}"

    meta = {
        "dataset_hash": dataset_hash,
        "seed": seed,
        "trained_at": utc_now_iso(),
        "feature_list": FEATURE_NAMES,
        "train_rows": len(X_train),
        "val_rows": len(X_val),
        "test_rows": len(X_test),
        "quantiles": quantiles,
    }

    return ForecastModelBundle(
        model_version=model_version,
        boosters=boosters,
        weekday_indices=weekday_indices,
        calibration_factors=calibration_factors,
        meta=meta,
        metrics=eval_metrics,
    )
