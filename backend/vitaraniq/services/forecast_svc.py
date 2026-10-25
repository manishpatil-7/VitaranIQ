"""
Forecast Service for VitaranIQ.
Orchestrates model training, artifact storage, model caching, and inference.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import pandas as pd
import sqlite3

from vitaraniq.core.config import load_params
from vitaraniq.core.ids import utc_now_iso
from vitaraniq.db.session import get_db_path, get_sqlite_connection
from vitaraniq.forecast.predict import predict_quantiles
from vitaraniq.forecast.train import ForecastModelBundle, train_quantile_models

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "models"


class ForecastService:
    _cached_models: Dict[str, ForecastModelBundle] = {}

    @classmethod
    def train_and_save(cls, dataset_id: str, seed: int = 42, db_path: Optional[Path] = None) -> Tuple[ForecastModelBundle, Dict[str, Any]]:
        conn = get_sqlite_connection(db_path)
        try:
            # 1. Load data from SQLite
            sales_df = pd.read_sql_query("SELECT store_id, sku_id, day, units, promo_flag FROM sales_daily WHERE dataset_id = ?", conn, params=(dataset_id,))
            calendar_df = pd.read_sql_query("SELECT day, date, dow, month, is_holiday, is_festival FROM calendar WHERE dataset_id = ?", conn, params=(dataset_id,))
            stores_df = pd.read_sql_query("SELECT store_id, size_mult FROM stores WHERE dataset_id = ?", conn, params=(dataset_id,))
            products_df = pd.read_sql_query("SELECT sku_id, category, price_paise, shelf_life_days FROM products WHERE dataset_id = ?", conn, params=(dataset_id,))
            
            # Map dow to sales_df for convenience
            cal_dow_map = dict(zip(calendar_df["day"], calendar_df["dow"]))
            sales_df["dow"] = sales_df["day"].map(cal_dow_map)

            cur = conn.cursor()
            cur.execute("SELECT dataset_hash FROM datasets WHERE dataset_id = ?", (dataset_id,))
            row = cur.fetchone()
            dataset_hash = row[0] if row else "unknown_hash"

            # 2. Train model bundle
            bundle = train_quantile_models(
                sales_df=sales_df,
                calendar_df=calendar_df,
                stores_df=stores_df,
                products_df=products_df,
                dataset_hash=dataset_hash,
                seed=seed,
            )

            # 3. Save artifacts
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            bundle.save(MODELS_DIR)
            cls._cached_models[bundle.model_version] = bundle

            # 4. Insert into SQLite models table
            cur.execute("""
                INSERT OR REPLACE INTO models (
                    model_version, dataset_id, trained_at, seed,
                    feature_list_json, params_json, lib_versions_json,
                    artifact_path, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bundle.model_version,
                dataset_id,
                bundle.meta["trained_at"],
                seed,
                json.dumps(bundle.meta["feature_list"]),
                json.dumps(bundle.meta),
                json.dumps({"lightgbm": "4.7.0"}),
                str(MODELS_DIR / bundle.model_version),
                "READY"
            ))

            # 5. Insert overall metrics
            m = bundle.metrics
            cur.execute("""
                INSERT OR REPLACE INTO forecast_metrics (
                    model_version, scope, scope_id, n_windows,
                    wape_model, wape_ma9, bias,
                    cov_p50, cov_p70, cov_p80, cov_p90,
                    pinball_loss
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bundle.model_version, "overall", "ALL", bundle.meta["test_rows"],
                m["wape_model"], m["wape_ma9"], m["bias"],
                m["cov_p50"], m["cov_p70"], m["cov_p80"], m["cov_p90"],
                m["pinball_loss"]
            ))

            conn.commit()
            return bundle, bundle.metrics
        finally:
            conn.close()

    @classmethod
    def get_model(cls, model_version: str) -> ForecastModelBundle:
        if model_version in cls._cached_models:
            return cls._cached_models[model_version]

        model_dir = MODELS_DIR / model_version
        if not model_dir.exists():
            raise FileNotFoundError(f"Model version {model_version} not found on disk")

        bundle = ForecastModelBundle.load(model_dir)
        cls._cached_models[model_version] = bundle
        return bundle

    @classmethod
    def get_active_model_version(cls, conn: Optional[sqlite3.Connection] = None) -> Optional[str]:
        close_conn = False
        if conn is None:
            conn = get_sqlite_connection()
            close_conn = True
        try:
            cur = conn.cursor()
            cur.execute("SELECT model_version FROM models WHERE status = 'READY' ORDER BY trained_at DESC LIMIT 1;")
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            if close_conn:
                conn.close()

    @classmethod
    def predict_for_day(
        cls,
        dataset_id: str,
        as_of_day: int = 703,
        model_version: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
        db_path: Optional[Path] = None,
    ) -> Dict[Tuple[str, str], Dict[str, int]]:
        close_conn = False
        if conn is None:
            conn = get_sqlite_connection(db_path)
            close_conn = True
        try:
            if model_version is None:
                model_version = cls.get_active_model_version(conn)
                if model_version is None:
                    raise ValueError("No trained model found in database. Train model first.")

            model = cls.get_model(model_version)

            # Load history and calendar
            sales_df = pd.read_sql_query("SELECT store_id, sku_id, day, units, promo_flag FROM sales_daily WHERE dataset_id = ?", conn, params=(dataset_id,))
            calendar_df = pd.read_sql_query("SELECT day, date, dow, month, is_holiday, is_festival FROM calendar WHERE dataset_id = ?", conn, params=(dataset_id,))
            stores_df = pd.read_sql_query("SELECT store_id, size_mult FROM stores WHERE dataset_id = ?", conn, params=(dataset_id,))
            products_df = pd.read_sql_query("SELECT sku_id, category, price_paise, shelf_life_days FROM products WHERE dataset_id = ?", conn, params=(dataset_id,))
            
            cal_dow_map = dict(zip(calendar_df["day"], calendar_df["dow"]))
            sales_df["dow"] = sales_df["day"].map(cal_dow_map)

            return predict_quantiles(
                model=model,
                sales_df=sales_df,
                calendar_df=calendar_df,
                stores_df=stores_df,
                products_df=products_df,
                as_of_day=as_of_day,
            )
        finally:
            if close_conn:
                conn.close()
