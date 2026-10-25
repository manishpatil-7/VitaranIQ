"""
Integration tests for FastAPI REST API endpoints.
Tests full pipeline through HTTP client: data -> forecast -> plan -> whatif.
"""

import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from vitaraniq.api.main import app
from vitaraniq.db.schema import init_db
from vitaraniq.db.session import get_sqlite_connection


@pytest.fixture
def client_with_tmp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_api.db"
        conn = get_sqlite_connection(test_db)
        init_db(conn)
        conn.close()

        # Monkeypatch get_db_path in session
        import vitaraniq.db.session as session_mod
        monkeypatch.setattr(session_mod, "get_db_path", lambda: test_db)


        with TestClient(app) as client:
            yield client


def test_api_end_to_end_workflow(client_with_tmp_db):
    client = client_with_tmp_db

    # 1. Health check
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # 2. Generate Data
    res = client.post("/api/v1/data/generate", json={"seed": 42})
    assert res.status_code == 200, res.text
    data_gen = res.json()

    assert data_gen["dataset_id"] == "ds_seed42"
    assert "sales_daily" in data_gen["row_counts"]

    # 3. Data Summary
    res = client.get("/api/v1/data/summary")
    assert res.status_code == 200
    summary = res.json()
    assert summary["warehouses_count"] == 4
    assert summary["stores_count"] == 25
    assert summary["products_count"] == 12

    # 4. Train Forecast
    res = client.post("/api/v1/forecast/train", json={"seed": 42})
    assert res.status_code == 200
    fct_res = res.json()
    assert "model_version" in fct_res

    # 5. Forecast Accuracy
    res = client.get("/api/v1/forecast/accuracy")
    assert res.status_code == 200
    acc_res = res.json()
    assert len(acc_res["metrics"]) > 0

    # 6. Forecast Series
    res = client.get("/api/v1/forecast/series?store_id=S01&sku_id=MILK-1L")
    assert res.status_code == 200
    series = res.json()
    assert len(series["history"]) > 0
    assert len(series["forecast"]) == 9
    assert series["chosen_quantile"] in ["P70", "P80", "P90"]

    # 7. Generate Plan
    res = client.post("/api/v1/plan", json={"as_of_day": 703, "supply_scenario": "normal", "workers": 4})
    assert res.status_code == 200
    plan_sum = res.json()
    plan_id = plan_sum["plan_id"]
    assert plan_sum["checker"]["status"] == "PASS"

    # 8. Get Plan Lines
    res = client.get(f"/api/v1/plan/{plan_id}/lines?page=1&page_size=20")
    assert res.status_code == 200
    lines_res = res.json()
    assert lines_res["total_lines"] > 0
    assert len(lines_res["lines"]) > 0

    # 9. Export CSV
    res = client.get(f"/api/v1/plan/{plan_id}/export")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "Warehouse_ID,Warehouse_Name" in res.text

    # 10. What-If Scenario (Warehouse Outage W1)
    res = client.post("/api/v1/whatif", json={
        "base_plan_id": plan_id,
        "outage_warehouse_id": "W1",
        "workers": 4,
    })
    assert res.status_code == 200, f"Whatif failed: {res.status_code} {res.text}"
    whatif = res.json()
    assert whatif["outage_warehouse_id"] == "W1"
    assert "delta_transport_paise" in whatif["comparison"]
