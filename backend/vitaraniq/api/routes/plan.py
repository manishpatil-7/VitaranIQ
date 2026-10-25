"""
Plan Generation, Query, and CSV Export Routes.
Conforms to System Architecture §6, SRS FR-OPT-01..07, and FR-REC-01..05.
"""

from typing import Any, Dict, List, Optional
import io
import csv
import json
import sqlite3
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from vitaraniq.db.session import get_sqlite_connection
from vitaraniq.services.plan_svc import PlanService
from vitaraniq.api.schemas import (
    PlanGenerateRequest,
    PlanSummaryResponse,
    PlanLinesResponse,
    PlanLineItem,
    PlanLineReason,
)

router = APIRouter(prefix="/plan", tags=["Plan"])


@router.post("", response_model=PlanSummaryResponse)
def generate_plan(req: PlanGenerateRequest):
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
        res = PlanService.generate_plan(
            dataset_id=dataset_id,
            as_of_day=req.as_of_day,
            supply_scenario=req.supply_scenario,
            workers=req.workers,
        )
        return PlanSummaryResponse(
            plan_id=res["plan_id"],
            as_of_day=res["as_of_day"],
            model_version=res["model_version"],
            solver=res["solver"],
            checker=res["checker"],
            stage_timings=res["stage_timings"],
            kpis=res["kpis"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{plan_id}", response_model=PlanSummaryResponse)
def get_plan(plan_id: str):
    conn = get_sqlite_connection()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

        timings = json.loads(row["stage_timings_json"]) if row["stage_timings_json"] else {}

        return PlanSummaryResponse(
            plan_id=row["plan_id"],
            as_of_day=row["as_of_day"],
            model_version=row["model_version"],
            solver={
                "status": row["solver_status"],
                "gap_pct": row["gap_pct"],
                "solve_time_s": row["solve_time_s"],
                "workers": row["solver_workers"],
            },
            checker={
                "status": row["checker_status"],
                "violations": 0,
            },
            stage_timings=timings,
            kpis={
                "total_cost_inr": round(row["total_cost_paise"] / 100.0, 2),
                "transport_inr": round(row["transport_paise"] / 100.0, 2),
                "unmet_units": row["unmet_units"],
                "n_lines": row["n_lines"],
            },
        )
    finally:
        conn.close()


@router.get("/{plan_id}/lines", response_model=PlanLinesResponse)
def get_plan_lines(
    plan_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    warehouse_id: Optional[str] = Query(None),
    store_id: Optional[str] = Query(None),
    sku_id: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
):
    conn = get_sqlite_connection()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Build dynamic query
        where_clauses = ["l.plan_id = ?"]
        params = [plan_id]

        if warehouse_id:
            where_clauses.append("l.warehouse_id = ?")
            params.append(warehouse_id)
        if store_id:
            where_clauses.append("l.store_id = ?")
            params.append(store_id)
        if sku_id:
            where_clauses.append("l.sku_id = ?")
            params.append(sku_id)
        if priority:
            where_clauses.append("l.priority = ?")
            params.append(priority)

        where_sql = " AND ".join(where_clauses)

        # Count total
        cur.execute(f"SELECT COUNT(*) FROM plan_lines l WHERE {where_sql}", tuple(params))
        total_lines = cur.fetchone()[0]

        # Fetch paginated rows with metadata
        offset = (page - 1) * page_size
        params.extend([page_size, offset])

        query = f"""
            SELECT l.line_no, l.sku_id, p.name AS sku_name,
                   l.warehouse_id, w.name AS warehouse_name,
                   l.store_id, s.name AS store_name,
                   l.batch_id, l.batch_expiry_day, l.qty,
                   l.trucks_on_lane, l.line_cost_paise, l.priority
            FROM plan_lines l
            JOIN plans pl ON l.plan_id = pl.plan_id
            JOIN products p ON pl.dataset_id = p.dataset_id AND l.sku_id = p.sku_id
            JOIN warehouses w ON pl.dataset_id = w.dataset_id AND l.warehouse_id = w.warehouse_id
            JOIN stores s ON pl.dataset_id = s.dataset_id AND l.store_id = s.store_id
            WHERE {where_sql}
            ORDER BY l.line_no ASC
            LIMIT ? OFFSET ?
        """
        cur.execute(query, tuple(params))
        line_rows = cur.fetchall()

        # Fetch reason codes for these lines
        line_nos = [r["line_no"] for r in line_rows]
        reasons_by_line = {}
        if line_nos:
            placeholders = ",".join("?" for _ in line_nos)
            cur.execute(f"""
                SELECT line_no, code, evidence_json
                FROM plan_line_reasons
                WHERE plan_id = ? AND line_no IN ({placeholders})
            """, (plan_id, *line_nos))
            for r in cur.fetchall():
                ln = r["line_no"]
                if ln not in reasons_by_line:
                    reasons_by_line[ln] = []
                reasons_by_line[ln].append(PlanLineReason(
                    code=r["code"],
                    evidence=json.loads(r["evidence_json"]) if r["evidence_json"] else {},
                ))

        items = []
        for r in line_rows:
            items.append(PlanLineItem(
                line_no=r["line_no"],
                sku_id=r["sku_id"],
                sku_name=r["sku_name"],
                warehouse_id=r["warehouse_id"],
                warehouse_name=r["warehouse_name"],
                store_id=r["store_id"],
                store_name=r["store_name"],
                batch_id=r["batch_id"],
                batch_expiry_day=r["batch_expiry_day"],
                qty=r["qty"],
                trucks_on_lane=r["trucks_on_lane"],
                line_cost_inr=round(r["line_cost_paise"] / 100.0, 2),
                priority=r["priority"],
                reason_codes=reasons_by_line.get(r["line_no"], []),
            ))

        return PlanLinesResponse(
            plan_id=plan_id,
            total_lines=total_lines,
            page=page,
            page_size=page_size,
            lines=items,
        )
    finally:
        conn.close()


@router.get("/{plan_id}/export")
def export_plan_csv(plan_id: str, warehouse_id: Optional[str] = Query(None)):
    """Export warehouse pick list CSV (FR-REC-05)."""
    conn = get_sqlite_connection()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        where_sql = "l.plan_id = ?"
        params = [plan_id]
        if warehouse_id:
            where_sql += " AND l.warehouse_id = ?"
            params.append(warehouse_id)

        cur.execute(f"""
            SELECT l.warehouse_id, w.name AS warehouse_name,
                   l.store_id, s.name AS store_name,
                   l.sku_id, p.name AS sku_name,
                   l.batch_id, l.batch_expiry_day, l.qty,
                   l.trucks_on_lane, l.priority
            FROM plan_lines l
            JOIN plans pl ON l.plan_id = pl.plan_id
            JOIN products p ON pl.dataset_id = p.dataset_id AND l.sku_id = p.sku_id
            JOIN warehouses w ON pl.dataset_id = w.dataset_id AND l.warehouse_id = w.warehouse_id
            JOIN stores s ON pl.dataset_id = s.dataset_id AND l.store_id = s.store_id
            WHERE {where_sql}
            ORDER BY l.warehouse_id, l.sku_id, l.batch_expiry_day ASC
        """, tuple(params))
        rows = cur.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Warehouse_ID", "Warehouse_Name", "Store_ID", "Store_Name",
            "SKU_ID", "SKU_Name", "Batch_ID", "Expiry_Day", "Quantity",
            "Trucks_Allocated", "Priority"
        ])
        for r in rows:
            writer.writerow([
                r["warehouse_id"], r["warehouse_name"], r["store_id"], r["store_name"],
                r["sku_id"], r["sku_name"], r["batch_id"], r["batch_expiry_day"],
                r["qty"], r["trucks_on_lane"], r["priority"]
            ])

        csv_content = output.getvalue()
        filename = f"pick_list_{plan_id}" + (f"_{warehouse_id}" if warehouse_id else "") + ".csv"
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    finally:
        conn.close()
