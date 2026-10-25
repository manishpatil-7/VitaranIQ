from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import yaml
from pydantic import BaseModel, Field


class WarehouseConfig(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    fleet: int = 30
    inbound_weight: float


class StoreAnchor(BaseModel):
    name: str
    lat: float
    lon: float
    region: str


class StoreConfig(BaseModel):
    count: int = 25
    base_storage_cap_ml: int = 18000000
    size_multipliers: List[float]
    anchor_cities: List[StoreAnchor]


class LaneConfig(BaseModel):
    distance_multiplier: float = 1.3
    max_eligible_km: float = 450.0
    transit_1_day_km_max: float = 200.0


class TruckConfig(BaseModel):
    capacity_ml: int = 4000000
    fixed_cost_paise: int = 80000
    cost_per_km_paise: int = 1400


class NetworkConfig(BaseModel):
    warehouses: List[WarehouseConfig]
    stores: StoreConfig
    lanes: LaneConfig
    trucks: TruckConfig


class ProductConfig(BaseModel):
    id: str
    name: str
    category: str
    unit_cost_paise: int
    price_paise: int
    volume_ml: int
    shelf_life_days: int
    min_life_days: int
    write_off_factor: float
    stockout_mult: int
    base_units_per_day: float
    target_quantile: float

    @property
    def margin_paise(self) -> int:
        return self.price_paise - self.unit_cost_paise


class DemandModelConfig(BaseModel):
    phi: float = 0.10
    weekday_multipliers: Dict[int, float]
    seasonality: Dict[str, Any]
    festival: Dict[str, Any]
    promo: Dict[str, Any]
    trend: Dict[str, Any]


class ForecastingConfig(BaseModel):
    window_days: int = 9
    quantiles: List[float] = [0.5, 0.7, 0.8, 0.9]
    service_level_floor: float = 0.7
    train_origins: List[int] = [29, 620]
    val_origins: List[int] = [630, 663]
    test_origins: List[int] = [673, 721]


class OptimizationConfig(BaseModel):
    solver_time_limit_s: float = 8.0
    relative_gap_limit: float = 0.005
    objective_scale_k: int = 100
    holding_cost_rate: float = 0.018
    fefo_epsilon_tie_break: int = 1
    default_workers: int = 4
    deterministic_workers: int = 1


class ScenarioConfig(BaseModel):
    inbound_factor: float


class SimulationConfig(BaseModel):
    start_day: int = 703
    end_day: int = 730
    plan_days: List[int] = [703, 710, 717, 724]
    seeds: List[int] = [11, 12, 13, 14, 15]
    scenarios: Dict[str, ScenarioConfig]


class SystemParams(BaseModel):
    network: NetworkConfig
    products: List[ProductConfig]
    demand_model: DemandModelConfig
    forecasting: ForecastingConfig
    optimization: OptimizationConfig
    simulation: SimulationConfig

    def get_product(self, sku_id: str) -> Optional[ProductConfig]:
        for p in self.products:
            if p.id == sku_id:
                return p
        return None

    def get_warehouse(self, wh_id: str) -> Optional[WarehouseConfig]:
        for w in self.network.warehouses:
            if w.id == wh_id:
                return w
        return None


def get_params_path() -> Path:
    env_path = os.getenv("PARAMS_PATH")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    
    # Try local search relative to current file and current working directory
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / "config" / "params.yaml",
        Path.cwd() / "config" / "params.yaml",
        Path.cwd() / "params.yaml",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("Could not locate config/params.yaml")


_cached_params: Optional[SystemParams] = None


def load_params(reload: bool = False) -> SystemParams:
    global _cached_params
    if _cached_params is not None and not reload:
        return _cached_params
    
    path = get_params_path()
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    _cached_params = SystemParams(**data)
    return _cached_params
