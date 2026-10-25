"""
Forecast evaluation metrics: WAPE, Bias, Empirical Coverage, Pinball Loss.
Implements FR-FCT-05 and PRD §8.2.
"""

from typing import Dict, List, Tuple
import numpy as np


def compute_wape(actuals: np.ndarray, preds: np.ndarray) -> float:
    tot_actual = float(np.sum(actuals))
    if tot_actual <= 0:
        return 0.0
    return float(np.sum(np.abs(actuals - preds)) / tot_actual)


def compute_bias(actuals: np.ndarray, preds: np.ndarray) -> float:
    tot_actual = float(np.sum(actuals))
    if tot_actual <= 0:
        return 0.0
    return float(np.sum(preds - actuals) / tot_actual)


def compute_coverage(actuals: np.ndarray, preds: np.ndarray) -> float:
    if len(actuals) == 0:
        return 0.0
    return float(np.mean(actuals <= preds))


def compute_pinball_loss(actuals: np.ndarray, preds: np.ndarray, alpha: float) -> float:
    diff = actuals - preds
    loss = np.maximum(alpha * diff, (alpha - 1.0) * diff)
    return float(np.mean(loss))


def evaluate_forecasts(
    actuals: np.ndarray,
    preds_dict: Dict[float, np.ndarray],
    ma9_preds: np.ndarray,
) -> Dict[str, float]:
    """Compute all evaluation metrics across quantiles."""
    p50 = preds_dict[0.5]
    p70 = preds_dict[0.7]
    p80 = preds_dict[0.8]
    p90 = preds_dict[0.9]

    wape_model = compute_wape(actuals, p50)
    wape_ma9 = compute_wape(actuals, ma9_preds)
    bias = compute_bias(actuals, p50)

    cov_p50 = compute_coverage(actuals, p50)
    cov_p70 = compute_coverage(actuals, p70)
    cov_p80 = compute_coverage(actuals, p80)
    cov_p90 = compute_coverage(actuals, p90)

    # Average pinball loss
    pinball = (
        compute_pinball_loss(actuals, p50, 0.5) +
        compute_pinball_loss(actuals, p70, 0.7) +
        compute_pinball_loss(actuals, p80, 0.8) +
        compute_pinball_loss(actuals, p90, 0.9)
    ) / 4.0

    return {
        "wape_model": round(wape_model, 4),
        "wape_ma9": round(wape_ma9, 4),
        "bias": round(bias, 4),
        "cov_p50": round(cov_p50, 4),
        "cov_p70": round(cov_p70, 4),
        "cov_p80": round(cov_p80, 4),
        "cov_p90": round(cov_p90, 4),
        "pinball_loss": round(pinball, 4),
    }
