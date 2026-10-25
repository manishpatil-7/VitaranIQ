"""
Newsvendor Critical-Ratio Service-Level Mapper.
Implements FR-SVL-01..04 and SRS Appendix A.
Computes CR = Cu / (Cu + Co) and maps to {0.7, 0.8, 0.9} with floor 0.7.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
import math

from vitaraniq.core.config import ProductConfig, SystemParams, load_params


@dataclass
class StoreSkuTarget:
    store_id: str
    sku_id: str
    p50_9d: int
    p70_9d: int
    p80_9d: int
    p90_9d: int
    critical_ratio: float
    chosen_quantile: float
    target_q: int
    onhand: int
    intransit: int
    cold_start: int = 0


@dataclass
class Targets:
    store_sku_targets: Dict[Tuple[str, str], StoreSkuTarget]

    def get(self, store_id: str, sku_id: str) -> StoreSkuTarget:
        return self.store_sku_targets[(store_id, sku_id)]


def compute_critical_ratio(p: ProductConfig, holding_cost_rate: float = 0.018) -> float:
    """
    Compute Newsvendor Critical Ratio:
    Cu = margin * g
    Co = unit_cost * w + holding_cost
    holding_cost = holding_cost_rate * unit_cost
    CR = Cu / (Cu + Co)
    """
    margin = p.margin_paise
    g = p.stockout_mult
    w = p.write_off_factor
    cost = p.unit_cost_paise
    
    Cu = margin * g
    holding_cost = round(holding_cost_rate * cost)
    Co = (cost * w) + holding_cost

    cr = Cu / (Cu + Co)
    return round(cr, 4)


def map_critical_ratio_to_quantile(cr: float, floor_quantile: float = 0.7) -> float:
    """
    Map CR to nearest in {0.7, 0.8, 0.9}.
    Ties go to the higher quantile.
    Enforces minimum service quantile floor (default 0.7).
    """
    if cr < floor_quantile:
        return floor_quantile

    candidates = [0.7, 0.8, 0.9]
    # Find nearest; in case of tie, pick the higher quantile
    best_q = 0.7
    best_dist = 999.0
    for q in candidates:
        dist = abs(cr - q)
        # Tie condition: dist <= best_dist ensures higher q is selected on ties
        if dist <= best_dist:
            best_dist = dist
            best_q = q
    return best_q


def make_targets(
    forecast_table: Dict[Tuple[str, str], Dict[str, int]],
    store_onhand: Dict[Tuple[str, str], int],
    intransit: Dict[Tuple[str, str], int],
    params: SystemParams = None,
) -> Targets:
    """
    Create Targets mapping for every (store_id, sku_id).
    """
    if params is None:
        params = load_params()

    targets_dict = {}
    cr_map = {}
    q_map = {}

    for p in params.products:
        cr = compute_critical_ratio(p, params.optimization.holding_cost_rate)
        q = map_critical_ratio_to_quantile(cr, params.forecasting.service_level_floor)
        cr_map[p.id] = cr
        q_map[p.id] = q

    for (store_id, sku_id), f_vals in forecast_table.items():
        cr = cr_map[sku_id]
        chosen_q = q_map[sku_id]
        
        p50 = f_vals.get("p50", 0)
        p70 = f_vals.get("p70", 0)
        p80 = f_vals.get("p80", 0)
        p90 = f_vals.get("p90", 0)

        if chosen_q == 0.7:
            target_q = p70
        elif chosen_q == 0.8:
            target_q = p80
        else:
            target_q = p90

        onhand = store_onhand.get((store_id, sku_id), 0)
        it = intransit.get((store_id, sku_id), 0)
        cold_start = f_vals.get("cold_start", 0)

        targets_dict[(store_id, sku_id)] = StoreSkuTarget(
            store_id=store_id,
            sku_id=sku_id,
            p50_9d=p50,
            p70_9d=p70,
            p80_9d=p80,
            p90_9d=p90,
            critical_ratio=cr,
            chosen_quantile=chosen_q,
            target_q=target_q,
            onhand=onhand,
            intransit=it,
            cold_start=cold_start,
        )

    return Targets(store_sku_targets=targets_dict)
