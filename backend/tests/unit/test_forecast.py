"""
Integration tests for LightGBM Quantile Forecaster.
Verifies training, calibration, monotonicity, and inference performance <= 2s.
"""

import time
import tempfile
from pathlib import Path
from vitaraniq.services.data_svc import DataService
from vitaraniq.services.forecast_svc import ForecastService


def test_forecast_train_and_predict_performance():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_forecast.db"
        ds = DataService.generate_and_save(seed=42, db_path=test_db)
        
        # Train
        t_start = time.perf_counter()
        bundle, metrics = ForecastService.train_and_save(dataset_id=ds["dataset_id"], seed=42, db_path=test_db)
        t_train = time.perf_counter() - t_start

        assert bundle.model_version.startswith("lgbm_q_")
        assert metrics["wape_model"] < metrics["wape_ma9"], f"Model WAPE {metrics['wape_model']} should beat MA9 {metrics['wape_ma9']}"
        assert metrics["cov_p90"] >= 0.85, f"P90 coverage {metrics['cov_p90']} should be >= 0.85"

        # Predict for Day 703
        t_pred_start = time.perf_counter()
        forecast_table = ForecastService.predict_for_day(dataset_id=ds["dataset_id"], as_of_day=703, db_path=test_db)
        t_pred = time.perf_counter() - t_pred_start

        # Performance requirement: <= 2.0 s (NFR-PERF-01)
        assert t_pred <= 2.0, f"Inference took {t_pred:.2f}s, expected <= 2.0s"
        assert len(forecast_table) == 300  # 25 stores * 12 skus

        # Monotonicity test: P50 <= P70 <= P80 <= P90
        for (s_id, sku_id), f_vals in forecast_table.items():
            assert f_vals["p50"] <= f_vals["p70"] <= f_vals["p80"] <= f_vals["p90"]
            assert f_vals["p50"] >= 0
