"""Performance review endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import (
    RequirePermissions,
    get_current_employee,
    get_current_user,
)
from app.core.pagination import Page, PaginationParams, paginate
from app.models.employee import Employee
from app.models.enums import ReviewStatus
from app.models.performance import Feedback, Goal, PerformanceReview, ReviewCycle
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.performance import (
    FeedbackCreate,
    FeedbackRead,
    GoalCreate,
    GoalRead,
    GoalUpdate,
    PerformanceReviewRead,
    ReviewAdvance,
    ReviewCycleCreate,
    ReviewCycleRead,
)
from app.services import employee_service, performance_service

router = APIRouter(prefix="/performance", tags=["Performance Reviews"])


# --------------------------------------------------------------------- cycles
@router.get("/cycles", response_model=List[ReviewCycleRead], summary="Review cycles")
def list_cycles(
    _: User = Depends(RequirePermissions("performance:read_own")),
    db: Session = Depends(get_db),
):
    return (
        db.execute(select(ReviewCycle).order_by(ReviewCycle.period_start.desc()))
        .scalars()
        .all()
    )


@router.post(
    "/cycles",
    response_model=ReviewCycleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a cycle",
)
def create_cycle(
    payload: ReviewCycleCreate,
    current_user: User = Depends(RequirePermissions("performance:manage")),
    db: Session = Depends(get_db),
):
    return performance_service.create_cycle(
        db, payload.model_dump(), actor_id=current_user.id
    )


@router.post(
    "/cycles/{cycle_id}/launch",
    response_model=List[PerformanceReviewRead],
    summary="Generate reviews for every eligible employee",
)
def launch_cycle(
    cycle_id: int,
    _: User = Depends(RequirePermissions("performance:manage")),
    db: Session = Depends(get_db),
):
    """Employees who joined after the period ended are skipped."""
    return performance_service.launch_cycle(db, cycle_id)


@router.post(
    "/cycles/{cycle_id}/close",
    response_model=ReviewCycleRead,
    summary="Close a cycle",
)
def close_cycle(
    cycle_id: int,
    _: User = Depends(RequirePermissions("performance:manage")),
    db: Session = Depends(get_db),
):
    """Blocked while any review is still in progress."""
    return performance_service.close_cycle(db, cycle_id)


# -------------------------------------------------------------------- reviews
@router.get(
    "/reviews/me", response_model=Page[PerformanceReviewRead], summary="Own reviews"
)
def my_reviews(
    params: PaginationParams = Depends(),
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    stmt = (
        select(PerformanceReview)
        .where(PerformanceReview.employee_id == employee.id)
        .order_by(PerformanceReview.id.desc())
    )
    rows, total = paginate(db, stmt, params)
    return Page[PerformanceReviewRead].create(
        [PerformanceReviewRead.model_validate(r) for r in rows], total, params
    )


@router.get(
    "/reviews", response_model=Page[PerformanceReviewRead], summary="Reviews (scoped)"
)
def list_reviews(
    params: PaginationParams = Depends(),
    cycle_id: Optional[int] = Query(None),
    status_filter: Optional[ReviewStatus] = Query(None, alias="status"),
    current_user: User = Depends(RequirePermissions("performance:read_team")),
    db: Session = Depends(get_db),
):
    visible_ids = db.execute(
        employee_service.scope_query(db, select(Employee.id), current_user)
    ).scalars().all()

    stmt = select(PerformanceReview).where(
        PerformanceReview.employee_id.in_(visible_ids)
    )
    if cycle_id is not None:
        stmt = stmt.where(PerformanceReview.cycle_id == cycle_id)
    if status_filter:
        stmt = stmt.where(PerformanceReview.status == status_filter)

    stmt = stmt.order_by(PerformanceReview.id.desc())
    rows, total = paginate(db, stmt, params)
    return Page[PerformanceReviewRead].create(
        [PerformanceReviewRead.model_validate(r) for r in rows], total, params
    )


@router.patch(
    "/reviews/{review_id}",
    response_model=PerformanceReviewRead,
    summary="Submit the current stage",
)
def advance_review(
    review_id: int,
    payload: ReviewAdvance,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Moves the review one stage forward:
    self_review → manager_review → hr_review → completed.

    Each transition checks the caller is the right party, so a manager cannot
    skip the self-review and an employee cannot sign off their own final
    rating. Completing the review writes the final rating back onto the
    employee record.
    """
    return performance_service.advance(
        db, review_id, payload.model_dump(exclude_unset=True), current_user
    )


# ---------------------------------------------------------------------- goals
@router.get("/goals/me", response_model=List[GoalRead], summary="Own goals")
def my_goals(
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    return (
        db.execute(
            select(Goal).where(Goal.employee_id == employee.id).order_by(Goal.id.desc())
        )
        .scalars()
        .all()
    )


@router.post(
    "/goals",
    response_model=GoalRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a goal",
)
def create_goal(
    payload: GoalCreate,
    employee_id: Optional[int] = Query(
        None, description="HR only; omit to create against your own record."
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Total goal weight across active goals cannot exceed 100%."""
    target_id = employee_id
    if target_id is None:
        profile = employee_service.get_by_user(db, current_user.id)
        if profile is None:
            from app.core.exceptions import PermissionDeniedError

            raise PermissionDeniedError("No employee profile is linked to your account.")
        target_id = profile.id

    return performance_service.create_goal(db, target_id, payload.model_dump())


@router.patch("/goals/{goal_id}", response_model=GoalRead, summary="Update a goal")
def update_goal(
    goal_id: int,
    payload: GoalUpdate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return performance_service.update_goal(
        db, goal_id, payload.model_dump(exclude_unset=True)
    )


# ------------------------------------------------------------------- feedback
@router.post(
    "/feedback",
    response_model=FeedbackRead,
    status_code=status.HTTP_201_CREATED,
    summary="Give feedback",
)
def give_feedback(
    payload: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = employee_service.get_by_user(db, current_user.id)
    return performance_service.give_feedback(
        db, profile.id if profile else None, payload.model_dump()
    )


@router.get(
    "/feedback/me", response_model=List[FeedbackRead], summary="Feedback received"
)
def my_feedback(
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    """Anonymous feedback is returned without its author."""
    rows = (
        db.execute(
            select(Feedback).where(
                Feedback.to_employee_id == employee.id,
                Feedback.is_visible_to_employee.is_(True),
            ).order_by(Feedback.id.desc())
        )
        .scalars()
        .all()
    )
    out = []
    for row in rows:
        payload = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        if row.is_anonymous:
            payload["from_employee_id"] = None
        out.append(payload)
    return out
