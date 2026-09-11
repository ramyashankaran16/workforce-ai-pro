"""
Retention interventions: plan lifecycle and before/after measurement.

A caution that belongs in the output, not just the code comments: an employee's
risk falling after an intervention does not establish that the intervention
caused it. High scores drift toward the mean on their own. Without a control
group this is correlation, and the effectiveness endpoint says so.
"""

import logging
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models.employee import Employee
from app.models.enums import (
    AlertStatus,
    InterventionOutcome,
    InterventionStatus,
    NotificationCategory,
    NotificationType,
)
from app.models.intervention import InterventionAction, InterventionPlan
from app.models.notification import Notification
from app.models.risk import RiskAlert
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)


def create_plan(db: Session, data: dict, actor_id: Optional[int] = None) -> InterventionPlan:
    employee = db.get(Employee, data["employee_id"])
    if employee is None or employee.is_deleted:
        raise NotFoundError("Employee not found.")

    if data.get("target_end_date") and data["target_end_date"] < data["start_date"]:
        raise BusinessRuleError("The target end date cannot precede the start date.")

    open_plan = db.execute(
        select(InterventionPlan).where(
            InterventionPlan.employee_id == employee.id,
            InterventionPlan.status.in_(
                [InterventionStatus.PLANNED, InterventionStatus.IN_PROGRESS]
            ),
        )
    ).scalars().first()
    if open_plan:
        raise BusinessRuleError(
            f"An intervention is already open for this employee "
            f"({open_plan.title}). Close it before starting another."
        )

    plan = InterventionPlan(
        **data,
        created_by_id=actor_id,
        # capture the score at the moment of intervention, so the comparison
        # later has a fixed starting point
        risk_score_before=employee.current_risk_score,
    )
    db.add(plan)
    db.flush()

    if plan.risk_alert_id:
        alert = db.get(RiskAlert, plan.risk_alert_id)
        if alert and alert.status == AlertStatus.NEW:
            alert.status = AlertStatus.IN_PROGRESS

    if plan.owner_id:
        db.add(
            Notification(
                user_id=plan.owner_id,
                title="Retention plan assigned",
                message=f"You own the plan '{plan.title}' for {employee.full_name}.",
                notification_type=NotificationType.INFO,
                category=NotificationCategory.ATTRITION_RISK,
                reference_type="intervention",
                reference_id=plan.id,
            )
        )

    db.commit()
    db.refresh(plan)
    return plan


def get_plan(db: Session, plan_id: int) -> InterventionPlan:
    plan = db.get(InterventionPlan, plan_id)
    if plan is None:
        raise NotFoundError("Intervention plan not found.")
    return plan


def update_plan(db: Session, plan_id: int, data: dict) -> InterventionPlan:
    plan = get_plan(db, plan_id)

    if plan.status in {InterventionStatus.COMPLETED, InterventionStatus.CANCELLED}:
        if "status" in data or "outcome" in data:
            raise BusinessRuleError(
                f"This plan is already {plan.status.value} and cannot be reopened."
            )

    new_status = data.get("status")
    if new_status == InterventionStatus.COMPLETED:
        outstanding = db.execute(
            select(func.count(InterventionAction.id)).where(
                InterventionAction.plan_id == plan.id,
                InterventionAction.is_completed.is_(False),
            )
        ).scalar() or 0
        if outstanding:
            raise BusinessRuleError(
                f"{outstanding} action(s) are still open on this plan."
            )

        employee = db.get(Employee, plan.employee_id)
        plan.risk_score_after = employee.current_risk_score if employee else None
        plan.completed_at = utcnow()

        if plan.risk_alert_id:
            alert = db.get(RiskAlert, plan.risk_alert_id)
            if alert and alert.status not in {AlertStatus.RESOLVED, AlertStatus.DISMISSED}:
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = utcnow()
                alert.resolution_notes = f"Closed by intervention: {plan.title}"

    for field, value in data.items():
        setattr(plan, field, value)

    db.commit()
    db.refresh(plan)
    return plan


def add_action(db: Session, plan_id: int, data: dict) -> InterventionAction:
    plan = get_plan(db, plan_id)
    if plan.status in {InterventionStatus.COMPLETED, InterventionStatus.CANCELLED}:
        raise BusinessRuleError(f"Cannot add actions to a {plan.status.value} plan.")

    highest = db.execute(
        select(func.max(InterventionAction.sequence)).where(
            InterventionAction.plan_id == plan.id
        )
    ).scalar() or 0

    action = InterventionAction(plan_id=plan.id, sequence=highest + 1, **data)
    db.add(action)

    if plan.status == InterventionStatus.PLANNED:
        plan.status = InterventionStatus.IN_PROGRESS

    if action.assigned_to_id:
        db.add(
            Notification(
                user_id=action.assigned_to_id,
                title="Retention action assigned",
                message=f"{action.title} (due {action.due_date or 'no date set'})",
                notification_type=NotificationType.INFO,
                category=NotificationCategory.TASK,
                reference_type="intervention_action",
                reference_id=plan.id,
            )
        )

    db.commit()
    db.refresh(action)
    return action


def complete_action(db: Session, action_id: int, notes: Optional[str] = None) -> InterventionAction:
    action = db.get(InterventionAction, action_id)
    if action is None:
        raise NotFoundError("Action not found.")
    if action.is_completed:
        raise BusinessRuleError("That action is already complete.")

    action.is_completed = True
    action.completed_at = utcnow()
    if notes:
        action.notes = notes

    db.commit()
    db.refresh(action)
    return action


def effectiveness(db: Session) -> dict:
    """
    Before/after comparison across completed plans.

    Reported as an observed change, not a proven effect.
    """
    plans = (
        db.execute(
            select(InterventionPlan).where(
                InterventionPlan.status == InterventionStatus.COMPLETED,
                InterventionPlan.risk_score_before.isnot(None),
                InterventionPlan.risk_score_after.isnot(None),
            )
        )
        .scalars()
        .all()
    )

    caveat = (
        "These are observed changes, not measured effects. High scores drift "
        "toward the mean without any intervention, and there is no control "
        "group here, so this shows correlation only."
    )

    if not plans:
        return {
            "completed_plans": 0,
            "by_type": [],
            "caveat": (
                "No completed plans with both a before and after score yet. "
                + caveat
            ),
        }

    by_type: Dict[str, List[float]] = {}
    improved = 0
    for plan in plans:
        change = plan.risk_score_after - plan.risk_score_before
        by_type.setdefault(plan.intervention_type.value, []).append(change)
        if change < 0:
            improved += 1

    summary = [
        {
            "intervention_type": name,
            "count": len(changes),
            "average_score_change": round(sum(changes) / len(changes), 2),
            "improved_count": sum(1 for c in changes if c < 0),
        }
        for name, changes in sorted(
            by_type.items(), key=lambda kv: sum(kv[1]) / len(kv[1])
        )
    ]

    return {
        "completed_plans": len(plans),
        "improved_count": improved,
        "improved_percent": round(improved / len(plans) * 100, 1),
        "average_score_change": round(
            sum(p.risk_score_after - p.risk_score_before for p in plans) / len(plans), 2
        ),
        "by_type": summary,
        "caveat": caveat,
    }
