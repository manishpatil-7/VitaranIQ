"""
Unit tests for 28-day Simulator and Stock Conservation Invariant (FR-SIM-08).
"""

import tempfile
from pathlib import Path
import pytest

from vitaraniq.db.session import get_sqlite_connection
from vitaraniq.services.data_svc import DataService
from vitaraniq.services.backtest_svc import BacktestService
from vitaraniq.sim.state import SimState
from vitaraniq.db.snapshot import load_snapshot_from_db


def test_stock_conservation_in_state():
    """Verify SimState maintains strict conservation arithmetic."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_sim_state.db"
        ds = DataService.generate_and_save(seed=42, db_path=test_db)

        conn = get_sqlite_connection(test_db)
        snapshot = load_snapshot_from_db(dataset_id=ds["dataset_id"], as_of_day=703, conn=conn)

        state = SimState(snapshot)

        # 1. Add inbound
        inbound = [{
            "warehouse_id": "W1",
            "sku_id": "MILK-500ML",
            "qty": 500,
            "expiry_day": 710,
        }]
        state.add_scheduled_inbound(inbound, day=703)

        # 2. Dispatch
        transit_map = {("W1", "S01"): 1}
        lines = [{
            "warehouse_id": "W1",
            "store_id": "S01",
            "sku_id": "MILK-500ML",
            "batch_id": state.wh_batches[("W1", "MILK-500ML")][0]["batch_id"],
            "batch_expiry_day": state.wh_batches[("W1", "MILK-500ML")][0]["expiry_day"],
            "qty": 50,
            "trucks_on_lane": 1,
            "line_cost_paise": 1000,
            "priority": "NORMAL",
        }]
        state.dispatch_plan_lines(lines, day=703, lane_transit=transit_map)

        # 3. Deliver on day 704
        arrived = state.process_arrivals(day=704)
        assert arrived == 50

        # 4. Demand FEFO
        sold, unmet = state.serve_demand_fefo({("S01", "MILK-500ML"): 20})
        assert sold == 20
        assert unmet == 0

        # 5. Expiry
        state.write_off_expired(day=720)

        # 6. Verify conservation
        is_conserved, errors = state.check_conservation_invariant()
        assert is_conserved is True, f"Conservation errors: {errors}"
        conn.close()


def test_simulation_b1_and_b2_execution():
    """Run single-seed simulation of B1 and B2 and verify database persistence and KPIs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_backtest.db"
        ds = DataService.generate_and_save(seed=42, db_path=test_db)

        res = BacktestService.run_backtest(
            dataset_id=ds["dataset_id"],
            seeds=[11],
            scenarios=["normal"],
            policies=["B1", "B2"],
            db_path=test_db,
        )

        assert res["status"] == "COMPLETE"
        assert res["n_simulations"] == 2

        # Verify database records
        conn = get_sqlite_connection(test_db)
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM sim_results WHERE run_id = ?", (res["run_id"],))
        n_res = cur.fetchone()[0]
        assert n_res == 2

        cur.execute("SELECT COUNT(*) FROM sim_daily WHERE run_id = ?", (res["run_id"],))
        n_daily = cur.fetchone()[0]
        assert n_daily == 2 * 28  # 2 policies * 28 days

        cur.execute("SELECT COUNT(*) FROM sim_plan_checks WHERE run_id = ?", (res["run_id"],))
        n_checks = cur.fetchone()[0]
        assert n_checks == 2 * 4  # 2 policies * 4 re-planning days

        # Check view v_sim_kpis
        cur.execute("SELECT policy, fill_rate, total_cost_paise FROM v_sim_kpis WHERE run_id = ?", (res["run_id"],))
        kpi_rows = cur.fetchall()
        assert len(kpi_rows) == 2

        for r in kpi_rows:
            assert r[1] > 0.5  # Fill rate > 50%
            assert r[2] > 0    # Total cost > 0

        conn.close()
