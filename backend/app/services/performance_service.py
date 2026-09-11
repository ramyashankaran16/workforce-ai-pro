"""
Performance reviews: cycle launch, staged transitions, goals and feedback.

The review moves through an explicit sequence. Each transition checks that the
caller is the right party for that stage, so a manager cannot skip the
self-review and an employee cannot sign off their own final rating.
"""

import logging
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessRuleError,
    DuplicateError,
    NotFoundError,
    PermissionDeniedError,
)
from app.models.employee import Employee
from app.models.enums import (
    GoalStatus,
    NotificationCategory,
    ReviewCycleStatus,
    ReviewStatus,
)
from app.models.performance import Feedback, Goal, PerformanceReview, ReviewCycle
from app.models.user import User
from app.services import notification_service
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)

# Which stage may follow which, and who is allowed to make the move.
TRANSITIONS: Dict[ReviewStatus, ReviewStatus] = {
    ReviewStatus.DRAFT: ReviewStatus.SELF_REVIEW,
    ReviewStatus.SELF_REVIEW: ReviewStatus.MANAGER_REVIEW,
    ReviewStatus.MANAGER_REVIEW: ReviewStatus.HR_REVIEW,
    ReviewStatus.HR_REVIEW: ReviewStatus.COMPLETED,
}


def create_cycle(db: Session, data: dict, actor_id: Optional[int] = None) -> ReviewCycle:
    existing = db.execute(
        select(ReviewCycle).where(ReviewCycle.name == data["name"])
    ).scalar_one_or_none()
    if existing:
        raise DuplicateError(f"A cycle named '{data['name']}' already exists.")
    if data["period_end"] <= data["period_start"]:
        raise BusinessRuleError("The period end must be after the period start.")

    cycle = ReviewCycle(**data, created_by_id=actor_id)
    db.add(cycle)
    db.commit()
    db.refresh(cycle)
    return cycle


def get_cycle(db: Session, cycle_id: int) -> ReviewCycle:
    cycle = db.get(ReviewCycle, cycle_id)
    if cycle is None:
        raise NotFoundError("Review cycle not found.")
    return cycle


def launch_cycle(db: Session, cycle_id: int) -> List[PerformanceReview]:
    """Create one review per eligible employee and open the cycle."""
    cycle = get_cycle(db, cycle_id)
    if cycle.status != ReviewCycleStatus.PLANNED:
        raise BusinessRuleError(f"This cycle is already {cycle.status.value}.")

    employees = (
        db.execute(
            select(Employee).where(
                Employee.is_deleted.is_(False),
                Employee.date_of_exit.is_(None),
                # someone who joined after the period ended has nothing to review
                Employee.date_of_joining <= cycle.period_end,
            )
        )
        .scalars()
        .all()
    )
    if not employees:
        raise BusinessRuleError("There are no eligible employees for this cycle.")

    created = []
    for employee in employees:
        review = PerformanceReview(
            cycle_id=cycle.id,
            employee_id=employee.id,
            reviewer_id=employee.manager_id,
            status=ReviewStatus.SELF_REVIEW,
        )
        db.add(review)
        created.append(review)

        if employee.user_id:
            notification_service.notify(
                db,
                employee.user_id,
                title=f"{cycle.name}: self-review open",
                message=(
                    f"Complete your self-review by "
                    f"{cycle.self_review_deadline or cycle.period_end}."
                ),
                category=NotificationCategory.PERFORMANCE,
                reference_type="review_cycle",
                reference_id=cycle.id,
                commit=False,
            )

    cycle.status = ReviewCycleStatus.OPEN
    db.commit()
    for review in created:
        db.refresh(review)
    return created


def get_review(db: Session, review_id: int) -> PerformanceReview:
    review = db.get(PerformanceReview, review_id)
    if review is None:
        raise NotFoundError("Review not found.")
    return review


def _assert_stage_actor(
    db: Session, review: PerformanceReview, user: User, target: ReviewStatus
) -> None:
    role = (user.role_name or "").lower()
    profile = db.execute(
        select(Employee).where(Employee.user_id == user.id)
    ).scalars().first()

    if target == ReviewStatus.MANAGER_REVIEW:
        # the employee submits their own self-review
        if profile is None or profile.id != review.employee_id:
            raise PermissionDeniedError("Only the employee can submit their self-review.")
    elif target == ReviewStatus.HR_REVIEW:
        if role in {"admin", "hr"}:
            return
        if profile is None or profile.id != review.reviewer_id:
            raise PermissionDeniedError(
                "Only the assigned reviewer or HR can submit the manager review."
            )
    elif target == ReviewStatus.COMPLETED:
        if role not in {"admin", "hr"}:
            raise PermissionDeniedError("Only HR can finalise a review.")


def advance(
    db: Session, review_id: int, data: dict, user: User
) -> PerformanceReview:
    review = get_review(db, review_id)

    if review.status == ReviewStatus.COMPLETED:
        raise BusinessRuleError("This review is already complete.")
    if review.status == ReviewStatus.CANCELLED:
        raise BusinessRuleError("This review was cancelled.")

    target = TRANSITIONS.get(review.status)
    if target is None:
        raise BusinessRuleError(f"No transition available from {review.status.value}.")

    _assert_stage_actor(db, review, user, target)

    cycle = get_cycle(db, review.cycle_id)
    for field in ("self_rating", "manager_rating", "final_rating"):
        value = data.get(field)
        if value is not None and not (1 <= value <= cycle.rating_scale_max):
            raise BusinessRuleError(
                f"{field} must be between 1 and {cycle.rating_scale_max}."
            )

    if target == ReviewStatus.MANAGER_REVIEW and data.get("self_rating") is None:
        raise BusinessRuleError("A self-rating is required to submit the self-review.")
    if target == ReviewStatus.HR_REVIEW and data.get("manager_rating") is None:
        raise BusinessRuleError("A manager rating is required at this stage.")

    for field, value in data.items():
        if value is not None:
            setattr(review, field, value)

    review.status = target

    if target == ReviewStatus.MANAGER_REVIEW:
        review.submitted_at = utcnow()
        reviewer = db.get(Employee, review.reviewer_id) if review.reviewer_id else None
        if reviewer and reviewer.user_id:
            employee = db.get(Employee, review.employee_id)
            notification_service.notify(
                db,
                reviewer.user_id,
                title="Self-review submitted",
                message=f"{employee.full_name} submitted their self-review.",
                category=NotificationCategory.PERFORMANCE,
                reference_type="review",
                reference_id=review.id,
                commit=False,
            )
    elif target == ReviewStatus.COMPLETED:
        review.completed_at = utcnow()
        if review.final_rating is None:
            review.final_rating = review.manager_rating

        employee = db.get(Employee, review.employee_id)
        if employee:
            employee.last_performance_rating = review.final_rating
            if employee.user_id:
                notification_service.notify(
                    db,
                    employee.user_id,
                    title="Review complete",
                    message=f"Your final rating is {review.final_rating}.",
                    category=NotificationCategory.PERFORMANCE,
                    reference_type="review",
                    reference_id=review.id,
                    commit=False,
                )

    db.commit()
    db.refresh(review)
    return review


def close_cycle(db: Session, cycle_id: int) -> ReviewCycle:
    cycle = get_cycle(db, cycle_id)
    if cycle.status != ReviewCycleStatus.OPEN:
        raise BusinessRuleError(f"This cycle is {cycle.status.value}, not open.")

    outstanding = db.execute(
        select(func.count(PerformanceReview.id)).where(
            PerformanceReview.cycle_id == cycle_id,
            PerformanceReview.status.notin_(
                [ReviewStatus.COMPLETED, ReviewStatus.CANCELLED]
            ),
        )
    ).scalar() or 0
    if outstanding:
        raise BusinessRuleError(f"{outstanding} review(s) are still in progress.")

    cycle.status = ReviewCycleStatus.CLOSED
    db.commit()
    db.refresh(cycle)
    return cycle


# ---------------------------------------------------------------------- goals
def create_goal(db: Session, employee_id: int, data: dict) -> Goal:
    employee = db.get(Employee, employee_id)
    if employee is None or employee.is_deleted:
        raise NotFoundError("Employee not found.")

    if data.get("due_date") and data.get("start_date"):
        if data["due_date"] < data["start_date"]:
            raise BusinessRuleError("The due date cannot precede the start date.")

    existing_weight = db.execute(
        select(func.coalesce(func.sum(Goal.weight_percent), 0)).where(
            Goal.employee_id == employee_id,
            Goal.status.notin_([GoalStatus.CANCELLED, GoalStatus.MISSED]),
        )
    ).scalar() or 0

    new_weight = data.get("weight_percent", 0)
    if existing_weight + new_weight > 100:
        raise BusinessRuleError(
            f"Goal weights would total {existing_weight + new_weight}%. "
            "They cannot exceed 100%."
        )

    goal = Goal(employee_id=employee_id, **data)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def update_goal(db: Session, goal_id: int, data: dict) -> Goal:
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise NotFoundError("Goal not found.")

    if data.get("progress_percent") == 100 and "status" not in data:
        data["status"] = GoalStatus.ACHIEVED

    if data.get("status") in {GoalStatus.ACHIEVED, GoalStatus.MISSED}:
        goal.completed_at = utcnow()

    for field, value in data.items():
        setattr(goal, field, value)

    db.commit()
    db.refresh(goal)
    return goal


def give_feedback(db: Session, from_employee_id: Optional[int], data: dict) -> Feedback:
    target = db.get(Employee, data["to_employee_id"])
    if target is None or target.is_deleted:
        raise NotFoundError("Employee not found.")
    if from_employee_id and from_employee_id == data["to_employee_id"]:
        raise BusinessRuleError("You cannot give yourself feedback.")

    feedback = Feedback(from_employee_id=from_employee_id, **data)
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback
