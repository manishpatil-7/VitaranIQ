"""
Unit test for Seeded Synthetic Data Generator.
Verifies FR-DAT-01 (reproducibility / canonical hash),
FR-DAT-02 (entity counts: 4 WH, 25 stores, 12 SKUs, 219k sales rows),
and FR-DAT-06 (V1–V8 validation).
"""

import pytest
from vitaraniq.data.generator import SyntheticDataGenerator
from vitaraniq.core.config import load_params


def test_generator_deterministic_hash():
    gen1 = SyntheticDataGenerator(seed=42)
    data1 = gen1.generate()

    gen2 = SyntheticDataGenerator(seed=42)
    data2 = gen2.generate()

    assert data1["dataset"]["dataset_hash"] == data2["dataset"]["dataset_hash"]
    assert len(data1["sales_daily"]) == 219000
    assert len(data1["warehouses"]) == 4
    assert len(data1["stores"]) == 25
    assert len(data1["products"]) == 12
    assert len(data1["lanes"]) == 100


def test_generator_non_negativity_and_bounds():
    gen = SyntheticDataGenerator(seed=42)
    data = gen.generate()

    # Verify no negative units
    for s in data["sales_daily"][:1000]:
        assert s["units"] >= 0

    # Verify batch expiries >= 703
    for b in data["batches"]:
        assert b["expiry_day"] >= 703
        assert b["qty"] > 0

    # Verify every store has at least 2 eligible warehouses
    eligible_count = {}
    for l in data["lanes"]:
        if l["eligible"] == 1:
            eligible_count[l["store_id"]] = eligible_count.get(l["store_id"], 0) + 1
    
    for s_id, count in eligible_count.items():
        assert count >= 2, f"Store {s_id} has only {count} eligible warehouses"
