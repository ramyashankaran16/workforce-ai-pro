"""
Workforce projection.

Ordinary least squares on the historical series, with prediction intervals
derived from the residual standard error rather than invented. Where there is
too little history for a trend to mean anything, the function says so and falls
back to the mean instead of extrapolating from three points.
"""

import math
from typing import Dict, List, Optional, Tuple

import numpy as np

MIN_POINTS_FOR_TREND = 4
Z_SCORES = {0.80: 1.282, 0.90: 1.645, 0.95: 1.960}


def fit_linear(values: List[float]) -> Tuple[float, float, float]:
    """Return (slope, intercept, residual_std)."""
    n = len(values)
    x = np.arange(n, dtype=float)
    y = np.asarray(values, dtype=float)

    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    residuals = y - fitted
    # n-2 degrees of freedom for a two-parameter fit
    dof = max(n - 2, 1)
    residual_std = float(np.sqrt((residuals ** 2).sum() / dof))
    return float(slope), float(intercept), residual_std


def project(
    values: List[float],
    periods: int,
    confidence: float = 0.90,
    floor: Optional[float] = 0.0,
    ceiling: Optional[float] = None,
) -> Dict[str, object]:
    """
    Project forward and return points with bounds.

    The interval widens with distance from the fitted data, which is the honest
    shape: a projection six months out is less certain than one month out.
    """
    if not values:
        return {"method": "none", "points": [], "note": "No history to project from."}

    z = Z_SCORES.get(round(confidence, 2), 1.645)
    n = len(values)

    if n < MIN_POINTS_FOR_TREND:
        mean = float(np.mean(values))
        spread = float(np.std(values, ddof=0)) or abs(mean) * 0.15
        points = []
        for step in range(1, periods + 1):
            points.append(
                _bounded(mean, mean - z * spread, mean + z * spread, floor, ceiling)
            )
        return {
            "method": "mean",
            "note": (
                f"Only {n} historical period(s). Too few to fit a trend, so the "
                "projection is the mean with a flat interval."
            ),
            "slope": 0.0,
            "points": points,
        }

    slope, intercept, residual_std = fit_linear(values)
    x = np.arange(n, dtype=float)
    x_mean = float(x.mean())
    sxx = float(((x - x_mean) ** 2).sum()) or 1.0

    points = []
    for step in range(1, periods + 1):
        position = n - 1 + step
        predicted = slope * position + intercept
        # standard error of a prediction at this position
        se = residual_std * math.sqrt(
            1 + 1 / n + ((position - x_mean) ** 2) / sxx
        )
        margin = z * se
        points.append(
            _bounded(predicted, predicted - margin, predicted + margin, floor, ceiling)
        )

    return {
        "method": "linear_regression",
        "note": None,
        "slope": round(slope, 4),
        "residual_std": round(residual_std, 4),
        "points": points,
    }


def _bounded(value, lower, upper, floor, ceiling) -> Dict[str, float]:
    def clamp(v):
        if floor is not None:
            v = max(v, floor)
        if ceiling is not None:
            v = min(v, ceiling)
        return round(float(v), 3)

    return {
        "predicted": clamp(value),
        "lower_bound": clamp(lower),
        "upper_bound": clamp(upper),
    }


def mape(actual: List[float], predicted: List[float]) -> Optional[float]:
    """Mean absolute percentage error, skipping zero actuals."""
    pairs = [(a, p) for a, p in zip(actual, predicted) if a not in (0, None)]
    if not pairs:
        return None
    return round(
        float(np.mean([abs((a - p) / a) for a, p in pairs]) * 100), 2
    )
