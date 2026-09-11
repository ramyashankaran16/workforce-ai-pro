"""Trained model registry and attrition predictions."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import (
    ModelAlgorithm,
    ModelStatus,
    PredictionSource,
    RiskLevel,
    enum_col,
)
from app.models.mixins import TimestampMixin
from app.models.types import JSONType
from app.utils.date_utils import utcnow


class ModelVersion(Base, TimestampMixin):
    """One trained artifact with its metrics. Exactly one may be deployed."""

    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    version: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    algorithm: Mapped[ModelAlgorithm] = mapped_column(enum_col(ModelAlgorithm), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    dataset_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    artifact_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    encoder_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    scaler_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    hyperparameters: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    feature_names: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    feature_importance: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    confusion_matrix: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    accuracy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    precision_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    f1_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    roc_auc: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cv_mean_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    train_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    test_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    training_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    status: Mapped[ModelStatus] = mapped_column(
        enum_col(ModelStatus), default=ModelStatus.QUEUED, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deployed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trained_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    dataset: Mapped[Optional["Dataset"]] = relationship(back_populates="model_versions")
    predictions: Mapped[List["AttritionPrediction"]] = relationship(
        back_populates="model_version"
    )
    batches: Mapped[List["PredictionBatch"]] = relationship(back_populates="model_version")

    def __repr__(self) -> str:
        return f"<ModelVersion {self.name} v{self.version} {self.status}>"


class PredictionBatch(Base, TimestampMixin):
    """Groups predictions produced in a single run."""

    __tablename__ = "prediction_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[PredictionSource] = mapped_column(
        enum_col(PredictionSource), default=PredictionSource.BATCH, nullable=False
    )

    total_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    high_risk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    medium_risk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    low_risk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    triggered_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    model_version: Mapped["ModelVersion"] = relationship(back_populates="batches")
    predictions: Mapped[List["AttritionPrediction"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PredictionBatch {self.reference} n={self.total_records}>"


class AttritionPrediction(Base, TimestampMixin):
    """A single employee's attrition probability at a point in time."""

    __tablename__ = "attrition_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("prediction_batches.id", ondelete="CASCADE"), nullable=True, index=True
    )

    attrition_probability: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    will_leave: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(
        enum_col(RiskLevel), default=RiskLevel.LOW, nullable=False, index=True
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    input_features: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    top_factors: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    predicted_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )
    source: Mapped[PredictionSource] = mapped_column(
        enum_col(PredictionSource), default=PredictionSource.BATCH, nullable=False
    )

    # Filled in later so model drift can be measured against reality
    actual_outcome: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    outcome_recorded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="predictions")
    model_version: Mapped["ModelVersion"] = relationship(back_populates="predictions")
    batch: Mapped[Optional["PredictionBatch"]] = relationship(back_populates="predictions")

    def __repr__(self) -> str:
        return f"<AttritionPrediction emp={self.employee_id} p={self.attrition_probability:.2f}>"
