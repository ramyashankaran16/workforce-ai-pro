"""Load a deployed artifact and score employees, singly or in batch."""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.ml import registry
from app.ml.preprocessing import align_frame
from app.models.enums import RiskLevel
from app.models.prediction import ModelVersion

logger = logging.getLogger(__name__)

# Probability bands. Deliberately not equal quarters: the top band is narrow so
# "critical" stays a short, actionable list rather than a wall of names.
RISK_BANDS = [
    (0.75, RiskLevel.CRITICAL),
    (0.55, RiskLevel.HIGH),
    (0.35, RiskLevel.MEDIUM),
    (0.0, RiskLevel.LOW),
]


def band_for(probability: float) -> RiskLevel:
    for floor, level in RISK_BANDS:
        if probability >= floor:
            return level
    return RiskLevel.LOW


def load_bundle(version: ModelVersion) -> dict:
    return registry.load_artifact(version.id, version.artifact_path)


def score_frame(
    version: ModelVersion, frame: pd.DataFrame
) -> Tuple[np.ndarray, List[str]]:
    """Return attrition probabilities for every row."""
    bundle = load_bundle(version)
    pipeline = bundle["pipeline"]
    expected: List[str] = bundle["feature_columns"]

    aligned = align_frame(frame, expected)
    probabilities = pipeline.predict_proba(aligned)[:, 1]
    return probabilities, expected


def predict_one(
    version: ModelVersion, frame: pd.DataFrame
) -> Dict[str, object]:
    probabilities, _ = score_frame(version, frame)
    probability = float(probabilities[0])
    bundle = load_bundle(version)
    threshold = float(bundle.get("decision_threshold", 0.5))

    return {
        "attrition_probability": round(probability, 4),
        "will_leave": probability >= threshold,
        "risk_level": band_for(probability),
        # Distance from the threshold: a 0.51 and a 0.95 are both "will leave",
        # but only one of them is a confident call.
        "confidence": round(float(abs(probability - threshold) * 2), 4),
        "decision_threshold": threshold,
    }
