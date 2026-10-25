"""
Data Generation and Summary Routes.
Conforms to System Architecture §6 and SRS FR-DAT-01..08.
"""

import sqlite3
from fastapi import APIRouter, HTTPException
from vitaraniq.db.session import get_sqlite_connection
from vitaraniq.services.data_svc import DataService
from vitaraniq.api.schemas import (
    DataGenerateRequest,
    DataGenerateResponse,
    DataSummaryResponse,
)

router = APIRouter(prefix="/data", tags=["Data"])


@router.post("/generate", response_model=DataGenerateResponse)
def generate_data(req: DataGenerateRequest):
    try:
        res = DataService.generate_and_save(seed=req.seed)
        return DataGenerateResponse(
            dataset_id=res["dataset_id"],
            seed=res["seed"],
            row_counts=res["row_counts"],
            sha256_hash=res["sha256_hash"],
            elapsed_seconds=res["elapsed_seconds"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary", response_model=DataSummaryResponse)
def get_data_summary():
    conn = get_sqlite_connection()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("SELECT * FROM datasets ORDER BY created_at DESC LIMIT 1;")
        row_ds = cur.fetchone()
        if not row_ds:
            raise HTTPException(status_code=404, detail="No dataset found. Run POST /api/v1/data/generate first.")

        dataset_id = row_ds["dataset_id"]

        cur.execute("SELECT COUNT(*) FROM warehouses WHERE dataset_id = ?", (dataset_id,))
        n_wh = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM stores WHERE dataset_id = ?", (dataset_id,))
        n_stores = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM products WHERE dataset_id = ?", (dataset_id,))
        n_products = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM sales_daily WHERE dataset_id = ?", (dataset_id,))
        n_sales = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM calendar WHERE dataset_id = ?", (dataset_id,))
        n_cal = cur.fetchone()[0]

        return DataSummaryResponse(
            dataset_id=dataset_id,
            seed=row_ds["seed"],
            warehouses_count=n_wh,
            stores_count=n_stores,
            products_count=n_products,
            sales_rows_count=n_sales,
            calendar_days=n_cal,
            sha256_hash=row_ds["dataset_hash"],
            created_at=row_ds["created_at"],
        )

    finally:
        conn.close()
