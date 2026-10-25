"""
Backtest Simulation Routes.
Conforms to System Architecture §6, SRS FR-SIM-01..09, and AIML Design §8.
"""

from typing import Any, Dict, List, Optional
import sqlite3
import json
from fastapi import APIRouter, HTTPException

from vitaraniq.db.session import get_sqlite_connection
from vitaraniq.services.backtest_svc import BacktestService
from vitaraniq.api.schemas import BacktestRunRequest, BacktestRunResponse

router = APIRouter(prefix="/backtest", tags=["Backtest"])


@router.post("", response_model=BacktestRunResponse)
def start_backtest(req: BacktestRunRequest):
    conn = get_sqlite_connection()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT dataset_id FROM datasets ORDER BY created_at DESC LIMIT 1;")
        row_ds = cur.fetchone()
        if not row_ds:
            raise HTTPException(status_code=404, detail="No dataset found. Generate data first.")
        dataset_id = row_ds["dataset_id"]
    finally:
        conn.close()

    try:
        res = BacktestService.run_backtest(
            dataset_id=dataset_id,
            seeds=req.seeds,
            scenarios=req.scenarios,
            policies=req.policies,
        )
        return BacktestRunResponse(
            run_id=res["run_id"],
            dataset_id=res["dataset_id"],
            status=res["status"],
            seeds=res["seeds"],
            scenarios=res["scenarios"],
            policies=res["policies"],
            n_simulations=res["n_simulations"],
            ablation=res["ablation"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{run_id}")
def get_backtest_run(run_id: str):
    try:
        return BacktestService.get_run_results(run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
def list_backtest_runs():
    conn = get_sqlite_connection()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT run_id, dataset_id, model_version, status,
                   seeds_json, scenarios_json, policies_json,
                   created_at, finished_at
            FROM backtest_runs
            ORDER BY created_at DESC
            LIMIT 20
        """)
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            r["seeds"] = json.loads(r["seeds_json"])
            r["scenarios"] = json.loads(r["scenarios_json"])
            r["policies"] = json.loads(r["policies_json"])
        return {"runs": rows}
    finally:
        conn.close()
