"""
Wastage coefficient and scaling computations for CP-SAT Optimizer.
Implements AIML Design §6.2 and §6.5.
"""

from typing import Dict, List, Tuple
import math


def compute_waste_coeff(
    unit_cost_paise: int,
    write_off_factor: float,
    rem_life_arrival: int,
    p50_9d: int,
    target_q: int,
) -> int:
    """
    Compute expected wastage coefficient Cw[b,s,p] in integer paise:
    Cw = round(unit_cost * w * pi)
    where pi = clip(1 - min(P50_9d * min(Lambda, 9)/9, target) / target, 0, 1) if Lambda <= 18 else 0
    """
    if rem_life_arrival > 18 or target_q <= 0:
        return 0

    l_eff = min(rem_life_arrival, 9)
    d50_eff = (p50_9d * l_eff) / 9.0
    expected_sales = min(d50_eff, float(target_q))
    pi = max(0.0, min(1.0, 1.0 - (expected_sales / float(target_q))))

    cw_paise = round(unit_cost_paise * write_off_factor * pi)
    return int(cw_paise)


def compute_holding_cost_paise(unit_cost_paise: int, rate: float = 0.018) -> int:
    """Holding cost over 9-day window: 0.2% per day -> 1.8% of unit cost."""
    return int(round(rate * unit_cost_paise))


def compute_lane_cost_paise(km: float, fixed_paise: int = 80000, per_km_paise: int = 1400) -> int:
    """Truck cost per trip: fixed ₹800 + ₹14/km."""
    return int(round(fixed_paise + per_km_paise * km))
