"""AI recommendation engine endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.core.pagination import Page, PaginationParams, paginate
from app.models.employee import Employee
from app.models.enums import (
    Priority,
    RecommendationCategory,
    RecommendationStatus,
)
from app.models.recommendation import Recommendation
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.recommendation import (
    FeedbackSubmit,
    FeedbackSummary,
    GenerationResult,
    RecommendationRead,
    StatusUpdate,
)
from app.services import employee_service, recommendation_service

router = APIRouter(prefix="/recommendations", tags=["AI Recommendations"])


@router.post(
    "/generate",
    response_model=GenerationResult,
    status_code=status.HTTP_201_CREATED,
    summary="Run the recommendation rules",
)
def generate(
    employee_id: Optional[int] = Query(None, description="One employee, or all"),
    _: User = Depends(RequirePermissions("recommendation:read")),
    db: Session = Depends(get_db),
):
    """
    Rule-driven rather than model-driven, deliberately. A recommendation has to
    be explainable to the manager acting on it: "bottom quartile of the band,
    no revision in 26 months" is actionable, "the model said 0.82" is not.

    Each recommendation carries its own evidence in `supporting_data`, and
    anything already open for the same reason is skipped rather than repeated.
    """
    return recommendation_service.generate(db, employee_id)


@router.get(
    "", response_model=Page[RecommendationRead], summary="List recommendations (scoped)"
)
def list_recommendations(
    params: PaginationParams = Depends(),
    category: Optional[RecommendationCategory] = Query(None),
    status_filter: Optional[RecommendationStatus] = Query(None, alias="status"),
    priority: Optional[Priority] = Query(None),
    employee_id: Optional[int] = Query(None),
    current_user: User = Depends(RequirePermissions("recommendation:read")),
    db: Session = Depends(get_db),
):
    visible_ids = db.execute(
        employee_service.scope_query(db, select(Employee.id), current_user)
    ).scalars().all()

    stmt = select(Recommendation).where(
        (Recommendation.employee_id.in_(visible_ids))
        | (Recommendation.employee_id.is_(None))
    )
    if category:
        stmt = stmt.where(Recommendation.category == category)
    if status_filter:
        stmt = stmt.where(Recommendation.status == status_filter)
    if priority:
        stmt = stmt.where(Recommendation.priority == priority)
    if employee_id is not None:
        stmt = stmt.where(Recommendation.employee_id == employee_id)

    stmt = stmt.order_by(Recommendation.id.desc())
    rows, total = paginate(db, stmt, params)
    return Page[RecommendationRead].create(
        [RecommendationRead.model_validate(r) for r in rows], total, params
    )


@router.get(
    "/feedback-summary",
    response_model=FeedbackSummary,
    summary="Which rules are earning their place",
)
def feedback_summary(
    _: User = Depends(RequirePermissions("recommendation:read")),
    db: Session = Depends(get_db),
):
    """
    Acceptance rate per category. A rule that is consistently rejected should
    be retired or retuned -- that is the loop this data exists to close.
    """
    return recommendation_service.feedback_summary(db)


@router.get(
    "/{recommendation_id}",
    response_model=RecommendationRead,
    summary="Recommendation with its evidence",
)
def get_recommendation(
    recommendation_id: int,
    current_user: User = Depends(RequirePermissions("recommendation:read")),
    db: Session = Depends(get_db),
):
    record = recommendation_service.get_recommendation(db, recommendation_id)
    if record.status == RecommendationStatus.NEW:
        record = recommendation_service.update_status(
            db, recommendation_id, RecommendationStatus.VIEWED, current_user.id
        )
    return record


@router.patch(
    "/{recommendation_id}",
    response_model=RecommendationRead,
    summary="Accept, reject or mark implemented",
)
def update_status(
    recommendation_id: int,
    payload: StatusUpdate,
    current_user: User = Depends(RequirePermissions("recommendation:read")),
    db: Session = Depends(get_db),
):
    return recommendation_service.update_status(
        db, recommendation_id, payload.status, current_user.id
    )


@router.post(
    "/{recommendation_id}/feedback",
    response_model=MessageResponse,
    summary="Rate a recommendation's usefulness",
)
def submit_feedback(
    recommendation_id: int,
    payload: FeedbackSubmit,
    current_user: User = Depends(RequirePermissions("recommendation:read")),
    db: Session = Depends(get_db),
):
    recommendation_service.add_feedback(
        db, recommendation_id, current_user.id, payload.model_dump()
    )
    return MessageResponse(message="Thanks - this tunes which rules stay active.")
