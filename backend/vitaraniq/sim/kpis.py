"""
Simulation KPI Aggregator and Ablation Breakdown.
Implements FR-SIM-07, FR-SIM-09, and Database Schema §5 (v_sim_kpis).
Zero-hallucination math: all metrics aggregate directly from simulation ledger entries.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import pandas as pd


@dataclass
class SimKPIs:
    policy: str
    seed: int
    supply_scenario: str
    units_demanded: int
    units_sold: int
    units_unmet: int
    units_delivered: int
    store_days_total: int
    store_days_stockout: int
    wastage_units: int
    wastage_paise: int
    transport_paise: int
    trips: int
    loaded_ml: int
    truck_capacity_ml_total: int
    lost_margin_paise: int
    margin_demanded_paise: int
    margin_sold_paise: int

    @property
    def fill_rate(self) -> float:
        return self.units_sold / max(1, self.units_demanded)

    @property
    def stockout_rate(self) -> float:
        return self.store_days_stockout / max(1, self.store_days_total)

    @property
    def cost_per_unit_delivered_paise(self) -> float:
        return self.transport_paise / max(1, self.units_delivered)

    @property
    def truck_fill(self) -> float:
        return self.loaded_ml / max(1, self.truck_capacity_ml_total)

    @property
    def total_cost_paise(self) -> int:
        return self.transport_paise + self.lost_margin_paise + self.wastage_paise

    @property
    def margin_weighted_fill_rate(self) -> float:
        return self.margin_sold_paise / max(1, self.margin_demanded_paise)


def compute_ablation_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute ablation metric across seeds and supply scenarios (FR-AB-01):
    - Total advantage: ΔCost(B1 vs VitaranIQ)
    - Forecasting advantage: ΔCost(B1 vs O-MA)
    - Optimization advantage: ΔCost(O-MA vs VitaranIQ)
    """
    df = pd.DataFrame(results)
    if df.empty or "total_cost_paise" not in df.columns:
        return {}

    # Group by scenario and policy
    grouped = df.groupby(["supply_scenario", "policy"])["total_cost_paise"].mean().unstack()

    ablation = {}
    for scenario in grouped.index:
        row = grouped.loc[scenario]
        cost_b1 = row.get("B1", 0)
        cost_b2 = row.get("B2", 0)
        cost_oma = row.get("O_MA", 0)
        cost_vit = row.get("VITARANIQ", 0)

        tot_adv = cost_b1 - cost_vit
        forecast_adv = cost_b1 - cost_oma
        opt_adv = cost_oma - cost_vit

        ablation[scenario] = {
            "cost_b1_inr": round(cost_b1 / 100.0, 2),
            "cost_b2_inr": round(cost_b2 / 100.0, 2),
            "cost_oma_inr": round(cost_oma / 100.0, 2),
            "cost_vitaraniq_inr": round(cost_vit / 100.0, 2),
            "total_savings_inr": round(tot_adv / 100.0, 2),
            "total_savings_pct": round(100.0 * tot_adv / max(1, cost_b1), 2),
            "forecasting_contribution_inr": round(forecast_adv / 100.0, 2),
            "optimization_contribution_inr": round(opt_adv / 100.0, 2),
        }

    return ablation
