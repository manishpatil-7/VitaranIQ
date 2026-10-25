"""
Integration tests for End-to-End Plan Generation.
Verifies FR-OPT-01..10, NFR-PERF-01 (latency <= 15s), and checker verification.
"""

import time
import tempfile
from pathlib import Path
from vitaraniq.services.data_svc import DataService
from vitaraniq.services.forecast_svc import ForecastService
from vitaraniq.services.plan_svc import PlanService


def test_plan_service_end_to_end_performance():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_plan.db"
        ds = DataService.generate_and_save(seed=42, db_path=test_db)
        
        # Train model
        ForecastService.train_and_save(dataset_id=ds["dataset_id"], seed=42, db_path=test_db)

        # Generate Plan for day 703
        t_start = time.perf_counter()
        plan_res = PlanService.generate_plan(
            dataset_id=ds["dataset_id"],
            as_of_day=703,
            time_limit_s=8.0,
            deterministic=True,
            db_path=test_db,
        )
        total_time = time.perf_counter() - t_start

        # Performance constraint: <= 15 s budget (NFR-PERF-01)
        assert total_time <= 15.0, f"Plan generation took {total_time:.2f}s, expected <= 15s"
        assert plan_res["solver"]["status"] in ("OPTIMAL", "FEASIBLE")
        assert plan_res["checker"]["status"] == "PASS"
        assert plan_res["checker"]["violations"] == 0
        assert len(plan_res["lines"]) > 0

        # Verify 100% of lines have >= 1 reason code
        for line in plan_res["lines"]:
            assert len(line["reason_codes"]) >= 1
            assert line["priority"] in ("URGENT", "HIGH", "NORMAL")
            assert line["line_cost_paise"] >= 0
