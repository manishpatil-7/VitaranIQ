"""
FastAPI Request and Response Pydantic Schemas.
Conforms to System Architecture §6, Database Schema §5, and OpenAPI contracts.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─── Health Schemas ───
class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    database_connected: bool = True
    dataset_id: Optional[str] = None
    model_version: Optional[str] = None


# ─── Data Schemas ───
class DataGenerateRequest(BaseModel):
    seed: int = Field(default=42, description="Random seed for data generation")


class DataGenerateResponse(BaseModel):
    dataset_id: str
    seed: int
    row_counts: Dict[str, int]
    sha256_hash: str
    elapsed_seconds: float


class DataSummaryResponse(BaseModel):
    dataset_id: str
    seed: int
    warehouses_count: int
    stores_count: int
    products_count: int
    sales_rows_count: int
    calendar_days: int
    sha256_hash: str
    created_at: str


# ─── Forecast Schemas ───
class ForecastTrainRequest(BaseModel):
    seed: int = Field(default=42, description="Seed for training split")


class ForecastTrainResponse(BaseModel):
    model_version: str
    dataset_id: str
    quantiles: List[float] = [0.50, 0.70, 0.80, 0.90]
    metrics: Dict[str, Any]
    training_time_seconds: float


class ForecastSeriesItem(BaseModel):
    day: int
    date: str
    actual: Optional[int] = None
    p50: Optional[float] = None
    p70: Optional[float] = None
    p80: Optional[float] = None
    p90: Optional[float] = None


class ForecastSeriesResponse(BaseModel):
    store_id: str
    sku_id: str
    critical_ratio: float
    chosen_quantile: str
    target_q: int
    history: List[Dict[str, Any]]
    forecast: List[Dict[str, Any]]


# ─── Plan Schemas ───
class PlanGenerateRequest(BaseModel):
    as_of_day: int = Field(default=703, ge=703, le=730)
    supply_scenario: str = Field(default="normal", pattern="^(normal|scarcity)$")
    workers: int = Field(default=4, ge=1, le=16)



class PlanSummaryResponse(BaseModel):
    plan_id: str
    as_of_day: int
    model_version: str
    solver: Dict[str, Any]
    checker: Dict[str, Any]
    stage_timings: Dict[str, float]
    kpis: Dict[str, Any]


class PlanLineReason(BaseModel):
    code: str
    evidence: Dict[str, Any]


class PlanLineItem(BaseModel):
    line_no: int
    sku_id: str
    sku_name: str
    warehouse_id: str
    warehouse_name: str
    store_id: str
    store_name: str
    batch_id: str
    batch_expiry_day: int
    qty: int
    trucks_on_lane: int
    line_cost_inr: float
    priority: str
    reason_codes: List[PlanLineReason]


class PlanLinesResponse(BaseModel):
    plan_id: str
    total_lines: int
    page: int
    page_size: int
    lines: List[PlanLineItem]


# ─── What-If Schemas ───
class WhatIfOutageRequest(BaseModel):
    base_plan_id: str
    outage_warehouse_id: str
    workers: int = Field(default=4, ge=1, le=16)


class WhatIfResponse(BaseModel):
    whatif_plan_id: str
    base_plan_id: str
    outage_warehouse_id: str
    comparison: Dict[str, Any]
    displaced_stores: List[Dict[str, Any]]
    new_routes: List[Dict[str, Any]]


# ─── Backtest Schemas ───
class BacktestRunRequest(BaseModel):
    seeds: Optional[List[int]] = Field(default=[11, 12, 13, 14, 15])
    scenarios: Optional[List[str]] = Field(default=["normal", "scarcity"])
    policies: Optional[List[str]] = Field(default=["B1", "B2", "O_MA", "VITARANIQ"])


class BacktestRunResponse(BaseModel):
    run_id: str
    dataset_id: str
    status: str
    seeds: List[int]
    scenarios: List[str]
    policies: List[str]
    n_simulations: int
    ablation: Dict[str, Any]
