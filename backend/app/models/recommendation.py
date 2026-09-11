"""AI-generated recommendations and feedback on their usefulness."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import (
    Priority,
    RecommendationCategory,
    RecommendationStatus,
    TargetScope,
    enum_col,
)
from app.models.mixins import TimestampMixin
from app.models.types import JSONType


class Recommendation(Base, TimestampMixin):
    """A suggested action produced by the recommendation engine."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    category: Mapped[RecommendationCategory] = mapped_column(
        enum_col(RecommendationCategory), nullable=False, index=True
    )
    scope: Mapped[TargetScope] = mapped_column(
        enum_col(TargetScope), default=TargetScope.EMPLOYEE, nullable=False
    )
    employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=True, index=True
    )
    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True
    )

    priority: Mapped[Priority] = mapped_column(
        enum_col(Priority), default=Priority.MEDIUM, nullable=False, index=True
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expected_impact: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    estimated_cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    supporting_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    status: Mapped[RecommendationStatus] = mapped_column(
        enum_col(RecommendationStatus),
        default=RecommendationStatus.NEW,
        nullable=False,
        index=True,
    )
    generated_by: Mapped[str] = mapped_column(String(60), default="rule_engine", nullable=False)
    model_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True
    )

    viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    actioned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    actioned_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    feedbacks: Mapped[List["RecommendationFeedback"]] = relationship(
        back_populates="recommendation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Recommendation {self.category} {self.title[:24]}>"


class RecommendationFeedback(Base, TimestampMixin):
    """Whether a recommendation was useful, so the engine can be tuned."""

    __tablename__ = "recommendation_feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_helpful: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    recommendation: Mapped["Recommendation"] = relationship(back_populates="feedbacks")

    def __repr__(self) -> str:
        return f"<RecommendationFeedback rec={self.recommendation_id}>"
