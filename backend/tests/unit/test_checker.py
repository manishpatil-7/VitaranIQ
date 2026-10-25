"""
Mutation tests for Independent Plan-Checker.
Implements FR-CHK-04: corrupts a valid plan once for each check (1)–(7)
and confirms that the checker detects every violation.
"""

import copy
import tempfile
from collections import defaultdict
from pathlib import Path
from vitaraniq.check.checks import check_plan
from vitaraniq.db.session import get_sqlite_connection
from vitaraniq.db.snapshot import load_snapshot_from_db
from vitaraniq.services.data_svc import DataService
from vitaraniq.services.forecast_svc import ForecastService
from vitaraniq.services.plan_svc import PlanService


def test_plan_checker_mutation_tests():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_checker.db"
        ds = DataService.generate_and_save(seed=42, db_path=test_db)
        ForecastService.train_and_save(dataset_id=ds["dataset_id"], seed=42, db_path=test_db)
        plan_res = PlanService.generate_plan(dataset_id=ds["dataset_id"], as_of_day=703, db_path=test_db)

        valid_lines = plan_res["lines"]
        assert len(valid_lines) > 0

        conn = get_sqlite_connection(test_db)
        snapshot = load_snapshot_from_db(dataset_id=ds["dataset_id"], as_of_day=703, conn=conn)
        conn.close()

        # Baseline: Valid plan passes
        base_check = check_plan(snapshot, valid_lines)
        assert base_check.passed is True
        assert len(base_check.violations) == 0

        # Mutation 1: Negative quantity (Check 1)
        m1_lines = copy.deepcopy(valid_lines)
        m1_lines[0]["qty"] = -10
        res1 = check_plan(snapshot, m1_lines)
        assert res1.passed is False
        assert any(v.check_id == 1 for v in res1.violations)

        # Mutation 2: Exceed batch stock (Check 2)
        m2_lines = copy.deepcopy(valid_lines)
        m2_lines[0]["qty"] = 9999999
        res2 = check_plan(snapshot, m2_lines)
        assert res2.passed is False
        assert any(v.check_id == 2 for v in res2.violations)

        # Mutation 3: Truck volume violation (Check 3)
        m3_lines = copy.deepcopy(valid_lines)
        target_w = m3_lines[0]["warehouse_id"]
        target_s = m3_lines[0]["store_id"]
        for line in m3_lines:
            if line["warehouse_id"] == target_w and line["store_id"] == target_s:
                line["trucks_on_lane"] = 0
        res3 = check_plan(snapshot, m3_lines)
        assert res3.passed is False
        assert any(v.check_id == 3 for v in res3.violations)


        # Mutation 4: Store capacity violation (Check 4)
        m4_lines = copy.deepcopy(valid_lines)
        # Add massive delivery to store
        large_line = copy.deepcopy(valid_lines[0])
        large_line["qty"] = 500000  # Will exceed store cap
        m4_lines.append(large_line)
        res4 = check_plan(snapshot, m4_lines)
        assert res4.passed is False
        assert any(v.check_id == 4 for v in res4.violations)

        # Mutation 5: Shelf life on arrival violation (Check 5)
        m5_lines = copy.deepcopy(valid_lines)
        # Set expiry to as_of + 1 (less than min_life_days)
        m5_lines[0]["batch_expiry_day"] = snapshot.as_of_day + 1
        res5 = check_plan(snapshot, m5_lines)
        assert res5.passed is False
        assert any(v.check_id == 5 for v in res5.violations)

        # Mutation 6: Ineligible lane (Check 6)
        m6_lines = copy.deepcopy(valid_lines)
        # Create an artificial line on an ineligible lane
        m6_lines[0]["warehouse_id"] = "W_NONEXISTENT"
        res6 = check_plan(snapshot, m6_lines)
        assert res6.passed is False
        assert any(v.check_id == 6 for v in res6.violations)

        # Mutation 7: FEFO Invariant (Check 7)
        # Dispatch a newer batch of a long-life SKU on an eligible lane while an older batch has stock
        m7_lines = copy.deepcopy(valid_lines)
        wh_batches = defaultdict(list)
        for b in snapshot.batches:
            wh_batches[(b["warehouse_id"], b["sku_id"])].append(b)

        target_wh_sku = None
        for (w_id, sku_id), b_list in wh_batches.items():
            p = snapshot.prod_map[sku_id]
            if p["shelf_life_days"] >= 30 and len(b_list) >= 2:
                target_wh_sku = (w_id, sku_id)
                break

        assert target_wh_sku is not None
        w_id, sku_id = target_wh_sku
        b_sorted = sorted(wh_batches[target_wh_sku], key=lambda x: x["expiry_day"])
        newer_b = b_sorted[-1]

        el_store = [s_id for (w, s_id), lane in snapshot.lanes.items() if w == w_id and lane.get("eligible") == 1][0]
        m7_lines.append({
            "line_no": len(m7_lines) + 1,
            "sku_id": sku_id,
            "warehouse_id": w_id,
            "store_id": el_store,
            "batch_id": newer_b["batch_id"],
            "batch_expiry_day": newer_b["expiry_day"],
            "qty": 1,
            "trucks_on_lane": 1,
            "line_cost_paise": 100,
            "priority": "NORMAL",
            "reason_codes": [],
        })
        res7 = check_plan(snapshot, m7_lines)
        assert res7.passed is False
        assert any(v.check_id == 7 for v in res7.violations)


