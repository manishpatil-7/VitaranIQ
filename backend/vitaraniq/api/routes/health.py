"""
Health Check Route.
GET /api/v1/health
"""

import sqlite3
from fastapi import APIRouter
from vitaraniq.db.session import get_db_path, get_sqlite_connection
from vitaraniq.api.schemas import HealthResponse

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
def get_health():
    db_connected = False
    latest_dataset = None
    latest_model = None

    try:
        conn = get_sqlite_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("SELECT dataset_id FROM datasets ORDER BY created_at DESC LIMIT 1;")
        row_ds = cur.fetchone()
        if row_ds:
            latest_dataset = row_ds["dataset_id"]

        cur.execute("SELECT model_version FROM models WHERE status = 'READY' ORDER BY trained_at DESC LIMIT 1;")
        row_m = cur.fetchone()
        if row_m:
            latest_model = row_m["model_version"]

        db_connected = True
        conn.close()
    except Exception:
        db_connected = False

    return HealthResponse(
        status="ok" if db_connected else "degraded",
        version="1.0.0",
        database_connected=db_connected,
        dataset_id=latest_dataset,
        model_version=latest_model,
    )
