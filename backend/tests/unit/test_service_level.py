"""
Unit tests for Newsvendor Service-Level selection.
Verifies FR-SVL-01..02 and exact critical-ratio / quantile outputs matching SRS Appendix A.
"""

from vitaraniq.core.config import load_params
from vitaraniq.service_level.newsvendor import compute_critical_ratio, map_critical_ratio_to_quantile


EXPECTED_QUANTILES = {
    "MILK-1L": (0.38, 0.7),
    "CURD-400G": (0.30, 0.7),
    "BREAD-400G": (0.57, 0.7),
    "BISC-250": (0.86, 0.9),
    "NOODLE-70": (0.82, 0.8),
    "RICE-5KG": (0.85, 0.8),
    "ATTA-5KG": (0.83, 0.8),
    "OIL-1L": (0.83, 0.8),
    "TEA-250G": (0.75, 0.8),
    "SOAP-100G": (0.71, 0.7),
    "JUICE-1L": (0.46, 0.7),
    "CHIPS-90G": (0.68, 0.7),
}


def test_service_level_appendix_a_exact_match():
    params = load_params()
    for sku_id, (exp_cr_approx, exp_q) in EXPECTED_QUANTILES.items():
        p = params.get_product(sku_id)
        assert p is not None
        cr = compute_critical_ratio(p, params.optimization.holding_cost_rate)
        # Verify CR is within 0.02 of table approximation
        assert abs(cr - exp_cr_approx) <= 0.02, f"SKU {sku_id} CR expected ~{exp_cr_approx}, got {cr}"
        
        q = map_critical_ratio_to_quantile(cr, params.forecasting.service_level_floor)
        assert q == exp_q, f"SKU {sku_id} mapped to {q}, expected {exp_q}"
