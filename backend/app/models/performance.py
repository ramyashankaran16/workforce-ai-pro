"""Performance review cycles, reviews, goals and feedback."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
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
    GoalStatus,
    ReviewCycleStatus,
    ReviewStatus,
    enum_col,
)
from app.models.mixins import TimestampMixin
from app.models.types import JSONType


class ReviewCycle(Base, TimestampMixin):
    """An appraisal window, e.g. FY25 H1."""

    __tablename__ = "review_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    self_review_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    manager_review_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    status: Mapped[ReviewCycleStatus] = mapped_column(
        enum_col(ReviewCycleStatus), default=ReviewCycleStatus.PLANNED, nullable=False, index=True
    )
    rating_scale_max: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    competencies: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    reviews: Mapped[List["PerformanceReview"]] = relationship(
        back_populates="cycle", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ReviewCycle {self.name}>"


class PerformanceReview(Base, TimestampMixin):
    """One employee's appraisal within a cycle."""

    __tablename__ = "performance_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(
        ForeignKey("review_cycles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[ReviewStatus] = mapped_column(
        enum_col(ReviewStatus), default=ReviewStatus.DRAFT, nullable=False, index=True
    )

    self_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    manager_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    final_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    competency_ratings: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    self_comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manager_comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hr_comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    strengths: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    improvement_areas: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    training_recommendations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    promotion_recommended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hike_recommended_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    cycle: Mapped["ReviewCycle"] = relationship(back_populates="reviews")
    employee: Mapped["Employee"] = relationship(
        back_populates="performance_reviews", foreign_keys=[employee_id]
    )
    reviewer: Mapped[Optional["Employee"]] = relationship(foreign_keys=[reviewer_id])

    def __repr__(self) -> str:
        return f"<PerformanceReview emp={self.employee_id} cycle={self.cycle_id}>"


class Goal(Base, TimestampMixin):
    """A measurable objective owned by an employee."""

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("performance_reviews.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    metric: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    target_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    achieved_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weight_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    status: Mapped[GoalStatus] = mapped_column(
        enum_col(GoalStatus), default=GoalStatus.NOT_STARTED, nullable=False, index=True
    )
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="goals")

    def __repr__(self) -> str:
        return f"<Goal {self.title[:24]} {self.status}>"


class Feedback(Base, TimestampMixin):
    """Continuous or 360-degree feedback between employees."""

    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    to_employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("performance_reviews.id", ondelete="SET NULL"), nullable=True
    )

    feedback_type: Mapped[str] = mapped_column(String(40), default="peer", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_visible_to_employee: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    from_employee: Mapped[Optional["Employee"]] = relationship(foreign_keys=[from_employee_id])
    to_employee: Mapped["Employee"] = relationship(foreign_keys=[to_employee_id])

    def __repr__(self) -> str:
        return f"<Feedback to={self.to_employee_id}>"
