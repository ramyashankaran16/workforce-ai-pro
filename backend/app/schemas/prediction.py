"""Model version and prediction schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    ModelAlgorithm,
    ModelStatus,
    PredictionSource,
    RiskLevel,
)
from app.schemas.common import ORMBase


class TrainRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    algorithm: ModelAlgorithm = ModelAlgorithm.RANDOM_FOREST
    horizon_days: int = Field(
        180, ge=30, le=730,
        description="Predict departure within this many days.",
    )
    voluntary_only: bool = Field(
        True,
        description=(
            "Count only resignations as attrition. Terminations are the "
            "company's decision, not the employee's."
        ),
    )
    include_protected_attributes: bool = Field(
        False,
        description=(
            "Include gender and marital status as features. Off by default: "
            "acting on a prediction driven by these carries discrimination risk."
        ),
    )
    decision_threshold: float = Field(
        0.5, ge=0.05, le=0.95,
        description="Probability above which an employee is flagged.",
    )
    hyperparameters: Dict[str, Any] = Field(default_factory=dict)
    dataset_id: Optional[int] = None


class ModelVersionRead(ORMBase):
    id: int
    name: str
    version: str
    algorithm: ModelAlgorithm
    description: Optional[str] = None
    status: ModelStatus
    is_active: bool
    accuracy: Optional[float] = None
    precision_score: Optional[float] = None
    recall_score: Optional[float] = None
    f1_score: Optional[float] = None
    roc_auc: Optional[float] = None
    cv_mean_score: Optional[float] = None
    train_rows: Optional[int] = None
    test_rows: Optional[int] = None
    training_duration_seconds: Optional[float] = None
    deployed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime


class ModelVersionDetail(ModelVersionRead):
    feature_names: Optional[Dict[str, Any]] = None
    feature_importance: Optional[Dict[str, Any]] = None
    confusion_matrix: Optional[Dict[str, Any]] = None
    hyperparameters: Optional[Dict[str, Any]] = None


class ExplanationFactor(BaseModel):
    feature: str
    label: str
    contribution: float
    direction: str
    employee_value: Optional[str] = None
    population_typical: Optional[str] = None


class PredictionRead(ORMBase):
    id: int
    employee_id: int
    model_version_id: int
    batch_id: Optional[int] = None
    attrition_probability: float
    will_leave: bool
    risk_level: RiskLevel
    confidence: Optional[float] = None
    explanation: Optional[str] = None
    predicted_at: datetime
    source: PredictionSource
    actual_outcome: Optional[bool] = None


class PredictionDetail(PredictionRead):
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None
    department_name: Optional[str] = None
    factors: List[ExplanationFactor] = []
    input_features: Optional[Dict[str, Any]] = None


class BatchRead(ORMBase):
    id: int
    reference: str
    model_version_id: int
    source: PredictionSource
    total_records: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    average_probability: Optional[float] = None
    duration_seconds: Optional[float] = None
    created_at: datetime


class OutcomeRecord(BaseModel):
    employee_id: int
    left: bool
