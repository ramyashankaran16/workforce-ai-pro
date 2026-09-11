"""
Recommendation engine.

Rule-driven rather than model-driven, and deliberately so: a recommendation
has to be explainable to the manager acting on it. "Raise this person's pay
because the model said 0.82" is not actionable; "they sit in the bottom
quartile of their band and have had no revision in 26 months" is.

Each rule states its own evidence in `supporting_data`, so the reasoning can
always be checked.
"""

import logging
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import (
    Priority,
    RecommendationCategory,
    RecommendationStatus,
    TargetScope,
)
from app.models.recommendation import Recommendation, RecommendationFeedback
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)

EXPIRY_DAYS = 45


def _exists(db: Session, employee_id: Optional[int], category, title: str) -> bool:
    """Do not re-raise a recommendation that is already open for the same thing."""
    return db.execute(
        select(Recommendation).where(
            Recommendation.employee_id == employee_id,
            Recommendation.category == category,
            Recommendation.title == title,
            Recommendation.status.in_(
                [RecommendationStatus.NEW, RecommendationStatus.VIEWED,
                 RecommendationStatus.ACCEPTED]
            ),
        )
    ).scalars().first() is not None


def _band_medians(db: Session) -> Dict[Optional[int], float]:
    rows = db.execute(
        select(Employee.designation_id, Employee.current_salary).where(
            Employee.is_deleted.is_(False),
            Employee.date_of_exit.is_(None),
            Employee.current_salary.isnot(None),
        )
    ).all()

    grouped: Dict[Optional[int], List[float]] = {}
    for designation_id, salary in rows:
        grouped.setdefault(designation_id, []).append(float(salary))

    medians = {}
    for designation_id, salaries in grouped.items():
        salaries.sort()
        mid = len(salaries) // 2
        medians[designation_id] = (
            salaries[mid]
            if len(salaries) % 2
            else (salaries[mid - 1] + salaries[mid]) / 2
        )
    return medians


# --------------------------------------------------------------------- rules
def _rule_underpaid(db: Session, employee: Employee, context: dict) -> Optional[dict]:
    median = context["band_medians"].get(employee.designation_id)
    if not median or not employee.current_salary:
        return None

    salary = float(employee.current_salary)
    if salary >= median * 0.9:
        return None

    gap_percent = round((median - salary) / median * 100, 1)
    return {
        "title": "Review compensation against the band median",
        "description": (
            f"{employee.full_name} is paid {gap_percent}% below the median for "
            f"their designation. Closing part of that gap is the most direct "
            f"lever available."
        ),
        "rationale": (
            "Pay below the band median is one of the strongest and most "
            "consistently observed drivers of voluntary exit."
        ),
        "category": RecommendationCategory.COMPENSATION,
        "priority": Priority.HIGH if gap_percent > 20 else Priority.MEDIUM,
        "expected_impact": f"Closes a {gap_percent}% gap to the band median",
        "estimated_cost": round((median * 0.9) - salary, 2),
        "supporting_data": {
            "current_salary": salary,
            "band_median": median,
            "gap_percent": gap_percent,
        },
    }


def _rule_promotion_overdue(db: Session, employee: Employee, context: dict) -> Optional[dict]:
    reference = employee.last_promotion_date or employee.date_of_joining
    if reference is None:
        return None

    months = round((date.today() - reference).days / 30.44)
    if months < 36:
        return None

    return {
        "title": "Consider for promotion or a role change",
        "description": (
            f"{employee.full_name} has been in the same role for {months} months "
            f"with no promotion recorded."
        ),
        "rationale": (
            "A long plateau without progression correlates strongly with "
            "voluntary exit, particularly among strong performers."
        ),
        "category": RecommendationCategory.RETENTION,
        "priority": Priority.HIGH if months > 48 else Priority.MEDIUM,
        "expected_impact": "Addresses a career-progression stall",
        "supporting_data": {
            "months_since_progression": months,
            "last_promotion_date": str(employee.last_promotion_date)
            if employee.last_promotion_date
            else None,
        },
    }


def _rule_overloaded(db: Session, employee: Employee, context: dict) -> Optional[dict]:
    if not employee.overtime_flag:
        return None
    if (employee.work_life_balance_score or 5) > 2:
        return None

    return {
        "title": "Rebalance workload",
        "description": (
            f"{employee.full_name} works regular overtime and rates their "
            f"work-life balance at {employee.work_life_balance_score}/5."
        ),
        "rationale": (
            "Sustained overtime combined with a low balance score is a "
            "burnout pattern, and burnout precedes resignation."
        ),
        "category": RecommendationCategory.WORKLOAD,
        "priority": Priority.HIGH,
        "expected_impact": "Reduces burnout risk",
        "supporting_data": {
            "overtime_flag": True,
            "work_life_balance_score": employee.work_life_balance_score,
        },
    }


def _rule_no_training(db: Session, employee: Employee, context: dict) -> Optional[dict]:
    hours = employee.training_hours_last_year
    if hours is None or hours >= 10:
        return None

    return {
        "title": "Schedule development time",
        "description": (
            f"{employee.full_name} recorded {hours:.0f} hours of training in the "
            f"past year."
        ),
        "rationale": (
            "Little or no development activity signals disengagement and "
            "limits internal mobility."
        ),
        "category": RecommendationCategory.TRAINING,
        "priority": Priority.MEDIUM,
        "expected_impact": "Improves engagement and internal mobility",
        "supporting_data": {"training_hours_last_year": hours},
    }


def _rule_low_engagement(db: Session, employee: Employee, context: dict) -> Optional[dict]:
    scores = [
        employee.job_satisfaction_score,
        employee.work_life_balance_score,
        employee.environment_satisfaction_score,
    ]
    known = [s for s in scores if s is not None]
    if not known:
        return None

    average = sum(known) / len(known)
    if average > 2.5:
        return None

    return {
        "title": "Hold a structured retention conversation",
        "description": (
            f"{employee.full_name}'s engagement scores average "
            f"{average:.1f}/5 across satisfaction, balance and environment."
        ),
        "rationale": (
            "Low engagement across several dimensions usually predates a "
            "resignation by months, which is the window in which it can still "
            "be addressed."
        ),
        "category": RecommendationCategory.ENGAGEMENT,
        "priority": Priority.CRITICAL if average <= 2 else Priority.HIGH,
        "expected_impact": "Surfaces the underlying issue while it is still fixable",
        "supporting_data": {"average_engagement": round(average, 2), "scores": known},
    }


def _rule_new_joiner_risk(db: Session, employee: Employee, context: dict) -> Optional[dict]:
    months = employee.tenure_months or 0
    if months > 6 or months < 1:
        return None
    if (employee.current_risk_score or 0) < 50:
        return None

    return {
        "title": "Strengthen onboarding support",
        "description": (
            f"{employee.full_name} joined {months} months ago and already "
            f"scores {employee.current_risk_score:.0f}/100 on risk."
        ),
        "rationale": (
            "First-year exits are usually onboarding failures rather than "
            "hiring failures, and they are recoverable if caught early."
        ),
        "category": RecommendationCategory.ENGAGEMENT,
        "priority": Priority.HIGH,
        "expected_impact": "Reduces early-tenure attrition",
        "supporting_data": {
            "tenure_months": months,
            "risk_score": employee.current_risk_score,
        },
    }


EMPLOYEE_RULES: List[Callable] = [
    _rule_underpaid,
    _rule_promotion_overdue,
    _rule_overloaded,
    _rule_no_training,
    _rule_low_engagement,
    _rule_new_joiner_risk,
]


def _department_rules(db: Session) -> List[dict]:
    """Recommendations aimed at a whole department rather than a person."""
    out = []
    rows = db.execute(
        select(
            Department.id,
            Department.name,
            func.count(Employee.id),
            func.avg(Employee.current_risk_score),
        )
        .join(Employee, Employee.department_id == Department.id)
        .where(Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None))
        .group_by(Department.id, Department.name)
    ).all()

    for dept_id, name, headcount, average in rows:
        if average is None or headcount < 3:
            continue
        if float(average) < 55:
            continue
        out.append(
            {
                "title": f"Run a retention review for {name}",
                "description": (
                    f"{name} averages {float(average):.0f}/100 on attrition risk "
                    f"across {headcount} people, which points at something "
                    f"structural rather than individual."
                ),
                "rationale": (
                    "When a whole team scores high, per-person interventions "
                    "treat symptoms. The cause is usually management load, pay "
                    "banding or workload distribution."
                ),
                "category": RecommendationCategory.RETENTION,
                "scope": TargetScope.DEPARTMENT,
                "department_id": dept_id,
                "priority": Priority.HIGH,
                "expected_impact": f"Addresses risk across {headcount} employees",
                "supporting_data": {
                    "headcount": int(headcount),
                    "average_risk_score": round(float(average), 2),
                },
            }
        )
    return out


def generate(db: Session, employee_id: Optional[int] = None) -> dict:
    """Run every rule and persist anything not already open."""
    context = {"band_medians": _band_medians(db)}

    if employee_id is not None:
        employee = db.get(Employee, employee_id)
        if employee is None or employee.is_deleted:
            raise NotFoundError("Employee not found.")
        employees = [employee]
    else:
        employees = (
            db.execute(
                select(Employee).where(
                    Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None)
                )
            )
            .scalars()
            .all()
        )

    created = 0
    skipped = 0

    for employee in employees:
        for rule in EMPLOYEE_RULES:
            result = rule(db, employee, context)
            if result is None:
                continue
            if _exists(db, employee.id, result["category"], result["title"]):
                skipped += 1
                continue

            db.add(
                Recommendation(
                    employee_id=employee.id,
                    scope=TargetScope.EMPLOYEE,
                    status=RecommendationStatus.NEW,
                    generated_by="rule_engine",
                    confidence=0.7,
                    expires_at=utcnow() + timedelta(days=EXPIRY_DAYS),
                    **result,
                )
            )
            created += 1

    if employee_id is None:
        for result in _department_rules(db):
            if _exists(db, None, result["category"], result["title"]):
                skipped += 1
                continue
            db.add(
                Recommendation(
                    status=RecommendationStatus.NEW,
                    generated_by="rule_engine",
                    confidence=0.65,
                    expires_at=utcnow() + timedelta(days=EXPIRY_DAYS),
                    **result,
                )
            )
            created += 1

    db.commit()
    return {
        "employees_evaluated": len(employees),
        "recommendations_created": created,
        "already_open": skipped,
        "rules_applied": len(EMPLOYEE_RULES),
    }


def get_recommendation(db: Session, recommendation_id: int) -> Recommendation:
    record = db.get(Recommendation, recommendation_id)
    if record is None:
        raise NotFoundError("Recommendation not found.")
    return record


def update_status(
    db: Session, recommendation_id: int, status: RecommendationStatus, user_id: int
) -> Recommendation:
    record = get_recommendation(db, recommendation_id)
    record.status = status
    if status == RecommendationStatus.VIEWED and record.viewed_at is None:
        record.viewed_at = utcnow()
    if status in {
        RecommendationStatus.ACCEPTED,
        RecommendationStatus.REJECTED,
        RecommendationStatus.IMPLEMENTED,
    }:
        record.actioned_at = utcnow()
        record.actioned_by_id = user_id

    db.commit()
    db.refresh(record)
    return record


def add_feedback(
    db: Session, recommendation_id: int, user_id: int, data: dict
) -> RecommendationFeedback:
    get_recommendation(db, recommendation_id)
    feedback = RecommendationFeedback(
        recommendation_id=recommendation_id, user_id=user_id, **data
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def feedback_summary(db: Session) -> dict:
    """
    What the feedback is actually for.

    Acceptance rate per category tells you which rules are earning their place.
    A rule that is consistently rejected should be retired or retuned -- that
    is the loop this data exists to close.
    """
    rows = db.execute(
        select(Recommendation.category, Recommendation.status, func.count(Recommendation.id))
        .group_by(Recommendation.category, Recommendation.status)
    ).all()

    by_category: Dict[str, Dict[str, int]] = {}
    for category, status, count in rows:
        key = str(category.value if hasattr(category, "value") else category)
        state = str(status.value if hasattr(status, "value") else status)
        by_category.setdefault(key, {})[state] = int(count)

    summary = []
    for category, states in by_category.items():
        total = sum(states.values())
        accepted = states.get("accepted", 0) + states.get("implemented", 0)
        rejected = states.get("rejected", 0)
        decided = accepted + rejected
        summary.append(
            {
                "category": category,
                "total": total,
                "accepted": accepted,
                "rejected": rejected,
                "acceptance_rate": (
                    round(accepted / decided * 100, 1) if decided else None
                ),
            }
        )

    helpful = db.execute(
        select(
            func.count(RecommendationFeedback.id),
            func.sum(
                func.cast(RecommendationFeedback.is_helpful, __import__("sqlalchemy").Integer)
            ),
        )
    ).one()

    return {
        "by_category": sorted(summary, key=lambda s: s["total"], reverse=True),
        "feedback_received": int(helpful[0] or 0),
        "rated_helpful": int(helpful[1] or 0),
        "note": (
            "Acceptance rate shows which rules are earning their place. A rule "
            "that is consistently rejected should be retired or retuned."
        ),
    }
