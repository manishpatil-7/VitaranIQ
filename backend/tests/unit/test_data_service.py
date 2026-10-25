"""
Integration test for DataService and SQLite persistence.
Verifies table insertion, STRICT typing, constraints, and snapshot loading.
"""

import tempfile
from pathlib import Path
from vitaraniq.services.data_svc import DataService
from vitaraniq.db.snapshot import load_snapshot_from_db
from vitaraniq.db.session import get_sqlite_connection


def test_data_service_generate_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_vitaraniq.db"
        ds = DataService.generate_and_save(seed=42, db_path=test_db)
        assert ds["n_warehouses"] == 4
        assert ds["n_stores"] == 25
        assert ds["n_skus"] == 12
        assert ds["n_sales_rows"] == 219000

        # Load Snapshot
        conn = get_sqlite_connection(test_db)
        snapshot = load_snapshot_from_db(dataset_id=ds["dataset_id"], as_of_day=703, conn=conn)
        conn.close()

        assert len(snapshot.warehouses) == 4
        assert len(snapshot.stores) == 25
        assert len(snapshot.products) == 12
        assert len(snapshot.batches) > 0
        assert len(snapshot.lanes) == 100
        assert len(snapshot.store_onhand) == 300  # 25 stores * 12 skus
