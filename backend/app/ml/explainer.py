"""
Per-employee explanation of a prediction.

Impurity-based feature importance describes the model as a whole; it cannot say
why *this* person scored 0.82. What follows is occlusion: each feature is
replaced in turn with the population median (or mode) and the model re-scored.
The drop or rise in probability is that feature's contribution for this
individual.

It costs one prediction per feature, which is cheap at ~25 features, and unlike
a hand-rolled heuristic it actually asks the model rather than guessing on its
behalf. SHAP would be the production choice; this is the same idea without the
dependency.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.ml.preprocessing import align_frame
from app.models.prediction import ModelVersion

logger = logging.getLogger(__name__)

# Human-readable labels for the raw feature names.
FEATURE_LABELS = {
    "tenure_months": "Time in role",
    "months_since_last_promotion": "Time since last promotion",
    "months_since_last_hike": "Time since last salary revision",
    "last_hike_percent": "Size of last increase",
    "salary_percentile_in_band": "Pay relative to peers in the same band",
    "job_satisfaction_score": "Job satisfaction",
    "work_life_balance_score": "Work-life balance",
    "environment_satisfaction_score": "Environment satisfaction",
    "last_performance_rating": "Performance rating",
    "absence_rate": "Absence rate",
    "late_rate": "Late arrivals",
    "overtime_ratio": "Overtime load",
    "leave_utilisation": "Leave taken",
    "distance_from_home_km": "Commute distance",
    "num_companies_worked": "Number of previous employers",
    "training_hours_last_year": "Training received",
    "team_size": "Team size",
    "department_name": "Department",
    "designation_title": "Role",
    "employment_type": "Employment type",
    "work_mode": "Work mode",
    "overtime_flag": "Works overtime",
    "has_manager": "Has an assigned manager",
    "business_travel_frequency": "Business travel",
    "education_level": "Education level",
    "age_years": "Age",
    "total_experience_years": "Total experience",
    "notice_period_days": "Notice period",
}


def label_for(feature: str) -> str:
    return FEATURE_LABELS.get(feature, feature.replace("_", " ").capitalize())


def explain(
    version: ModelVersion,
    row: pd.DataFrame,
    baseline: pd.DataFrame,
    top_n: int = 6,
) -> Dict[str, object]:
    """
    Contributions for one employee.

    `baseline` is the population frame used to derive a neutral value for each
    feature. Positive contribution = this feature pushes risk up.
    """
    from app.ml.predictor import load_bundle

    bundle = load_bundle(version)
    pipeline = bundle["pipeline"]
    expected: List[str] = bundle["feature_columns"]

    aligned = align_frame(row, expected)
    base_probability = float(pipeline.predict_proba(aligned)[:, 1][0])

    neutral_baseline = align_frame(baseline, expected)
    contributions: List[Dict[str, object]] = []

    for feature in expected:
        probe = aligned.copy()
        column = neutral_baseline[feature]

        if pd.api.types.is_numeric_dtype(column):
            neutral = column.median()
        else:
            modes = column.mode()
            neutral = modes.iloc[0] if not modes.empty else column.iloc[0]

        if pd.isna(neutral):
            continue

        probe[feature] = neutral
        try:
            probed = float(pipeline.predict_proba(probe)[:, 1][0])
        except Exception:  # a feature the pipeline cannot re-encode
            continue

        delta = base_probability - probed
        if abs(delta) < 1e-6:
            continue

        actual = row[feature].iloc[0] if feature in row.columns else None
        contributions.append(
            {
                "feature": feature,
                "label": label_for(feature),
                "contribution": round(delta, 5),
                "direction": "increases risk" if delta > 0 else "reduces risk",
                "employee_value": _readable(actual),
                "population_typical": _readable(neutral),
            }
        )

    contributions.sort(key=lambda c: abs(c["contribution"]), reverse=True)
    top = contributions[:top_n]

    return {
        "base_probability": round(base_probability, 4),
        "factors": top,
        "narrative": _narrative(top),
    }


def _readable(value) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        return str(round(float(value), 2))
    return str(value)


def _narrative(factors: List[Dict[str, object]]) -> str:
    raising = [f for f in factors if f["contribution"] > 0][:3]
    lowering = [f for f in factors if f["contribution"] < 0][:2]

    if not raising and not lowering:
        return "No single factor stands out for this employee."

    parts = []
    if raising:
        names = ", ".join(str(f["label"]).lower() for f in raising)
        parts.append(f"Risk is driven mainly by {names}")
    if lowering:
        names = ", ".join(str(f["label"]).lower() for f in lowering)
        parts.append(f"working against that, {names} lower the score")
    return ". ".join(parts) + "."
