"""
Rule evaluation for the smart alert engine.

Two things stop this becoming a notification firehose: a per-rule cooldown, so
the same rule cannot re-fire for the same employee within N hours, and
de-duplication against alerts that are still open. HR that receives 200 emails
about one scoring run stops reading them.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models.alert_rule import AlertRule, AlertTrigger
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import (
    AlertStatus,
    NotificationCategory,
    NotificationType,
    RuleOperator,
    RuleTargetMetric,
    TargetScope,
)
from app.models.notification import Notification
from app.models.prediction import AttritionPrediction
from app.models.risk import RiskAlert
from app.models.role import Role
from app.models.user import User
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)


def compare(value: float, operator: RuleOperator, threshold: float,
            secondary: Optional[float] = None) -> bool:
    if operator == RuleOperator.GREATER_THAN:
        return value > threshold
    if operator == RuleOperator.GREATER_OR_EQUAL:
        return value >= threshold
    if operator == RuleOperator.LESS_THAN:
        return value < threshold
    if operator == RuleOperator.LESS_OR_EQUAL:
        return value <= threshold
    if operator == RuleOperator.EQUAL:
        return value == threshold
    if operator == RuleOperator.NOT_EQUAL:
        return value != threshold
    if operator == RuleOperator.BETWEEN:
        return threshold <= value <= (secondary if secondary is not None else threshold)
    return False


def metric_value(db: Session, employee: Employee, metric: RuleTargetMetric) -> Optional[float]:
    if metric == RuleTargetMetric.RISK_SCORE:
        return employee.current_risk_score
    if metric == RuleTargetMetric.ATTRITION_PROBABILITY:
        latest = db.execute(
            select(AttritionPrediction)
            .where(AttritionPrediction.employee_id == employee.id)
            .order_by(AttritionPrediction.predicted_at.desc())
        ).scalars().first()
        return latest.attrition_probability if latest else None
    if metric == RuleTargetMetric.TENURE_MONTHS:
        return float(employee.tenure_months or 0)
    if metric == RuleTargetMetric.PERFORMANCE_RATING:
        return employee.last_performance_rating
    if metric == RuleTargetMetric.OVERTIME_HOURS:
        from app.models.attendance import Attendance

        total = db.execute(
            select(func.sum(Attendance.overtime_hours)).where(
                Attendance.employee_id == employee.id
            )
        ).scalar()
        return float(total or 0)
    if metric == RuleTargetMetric.ABSENCE_RATE:
        from app.ml import feature_engineering

        frame = feature_engineering.build_feature_frame(db, employees=[employee])
        if frame.empty:
            return None
        value = frame.iloc[0].get("absence_rate")
        return None if value is None or value != value else float(value)
    if metric == RuleTargetMetric.LEAVE_BALANCE:
        from app.models.leave import LeaveBalance

        rows = db.execute(
            select(LeaveBalance).where(LeaveBalance.employee_id == employee.id)
        ).scalars().all()
        return float(sum(b.available for b in rows)) if rows else None
    return None


def _in_scope(db: Session, rule: AlertRule, employee: Employee) -> bool:
    if rule.scope == TargetScope.ORGANISATION:
        return True
    if rule.scope == TargetScope.DEPARTMENT:
        return employee.department_id == rule.department_id
    if rule.scope == TargetScope.EMPLOYEE:
        return employee.id == rule.employee_id
    return True


def _recently_triggered(db: Session, rule: AlertRule, employee_id: int) -> bool:
    if not rule.cooldown_hours:
        return False
    since = utcnow() - timedelta(hours=rule.cooldown_hours)
    existing = db.execute(
        select(AlertTrigger).where(
            AlertTrigger.rule_id == rule.id,
            AlertTrigger.employee_id == employee_id,
            AlertTrigger.created_at >= since,
        )
    ).scalars().first()
    return existing is not None


def _has_open_alert(db: Session, employee_id: int, rule_id: int) -> bool:
    return db.execute(
        select(RiskAlert).where(
            RiskAlert.employee_id == employee_id,
            RiskAlert.alert_rule_id == rule_id,
            RiskAlert.status.in_([AlertStatus.NEW, AlertStatus.ACKNOWLEDGED,
                                  AlertStatus.IN_PROGRESS]),
        )
    ).scalars().first() is not None


def _recipients(db: Session, rule: AlertRule, employee: Employee) -> List[User]:
    """Who to notify: the roles named on the rule, plus the line manager."""
    role_names = (rule.notify_roles or {}).get("roles", ["hr"])
    users = (
        db.execute(
            select(User).join(Role).where(
                Role.name.in_(role_names),
                User.is_deleted.is_(False),
            )
        )
        .scalars()
        .all()
    )

    if employee.manager_id:
        manager = db.get(Employee, employee.manager_id)
        if manager and manager.user_id:
            manager_user = db.get(User, manager.user_id)
            if manager_user and manager_user not in users:
                users.append(manager_user)
    return users


def _render(rule: AlertRule, employee: Employee, value: float) -> str:
    template = rule.message_template or (
        "{employee} triggered '{rule}': {metric} is {value}, "
        "threshold {operator} {threshold}."
    )
    return template.format(
        employee=employee.full_name,
        employee_code=employee.employee_code,
        rule=rule.name,
        metric=rule.metric.value,
        value=round(value, 4),
        operator=rule.operator.value,
        threshold=rule.threshold_value,
    )


def evaluate_rules(
    db: Session, rule_id: Optional[int] = None, notify: bool = True
) -> dict:
    """Run active rules across every in-scope employee."""
    stmt = select(AlertRule).where(AlertRule.is_active.is_(True))
    if rule_id is not None:
        stmt = select(AlertRule).where(AlertRule.id == rule_id)

    rules = db.execute(stmt).scalars().all()
    if not rules:
        return {"rules_evaluated": 0, "triggers": 0, "alerts_created": 0,
                "notifications_sent": 0, "suppressed": 0}

    employees = (
        db.execute(
            select(Employee).where(
                Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None)
            )
        )
        .scalars()
        .all()
    )

    triggers = 0
    alerts = 0
    notifications = 0
    suppressed = 0

    for rule in rules:
        fired_for_rule = 0
        for employee in employees:
            if not _in_scope(db, rule, employee):
                continue

            value = metric_value(db, employee, rule.metric)
            if value is None:
                continue
            if not compare(value, rule.operator, rule.threshold_value,
                           rule.secondary_threshold):
                continue

            if _recently_triggered(db, rule, employee.id) or _has_open_alert(
                db, employee.id, rule.id
            ):
                suppressed += 1
                continue

            message = _render(rule, employee, value)
            trigger = AlertTrigger(
                rule_id=rule.id,
                employee_id=employee.id,
                department_id=employee.department_id,
                metric_value=round(value, 4),
                threshold_value=rule.threshold_value,
                message=message,
                context={
                    "metric": rule.metric.value,
                    "operator": rule.operator.value,
                    "employee_code": employee.employee_code,
                },
            )
            db.add(trigger)
            db.flush()
            triggers += 1
            fired_for_rule += 1

            alert = RiskAlert(
                employee_id=employee.id,
                alert_rule_id=rule.id,
                title=f"{rule.name}: {employee.full_name}",
                message=message,
                risk_level=_level_for(employee),
                priority=rule.priority,
                status=AlertStatus.NEW,
            )
            db.add(alert)
            alerts += 1

            if notify:
                for user in _recipients(db, rule, employee):
                    db.add(
                        Notification(
                            user_id=user.id,
                            title=rule.name,
                            message=message,
                            notification_type=NotificationType.ALERT,
                            category=NotificationCategory.ATTRITION_RISK,
                            priority=rule.priority,
                            channel=rule.channel,
                            reference_type="employee",
                            reference_id=employee.id,
                            action_url=f"/employees/{employee.id}",
                        )
                    )
                    notifications += 1
                trigger.notifications_sent = notifications

        if fired_for_rule:
            rule.trigger_count = (rule.trigger_count or 0) + fired_for_rule
            rule.last_triggered_at = utcnow()

    db.commit()
    return {
        "rules_evaluated": len(rules),
        "triggers": triggers,
        "alerts_created": alerts,
        "notifications_sent": notifications,
        "suppressed": suppressed,
    }


def _level_for(employee: Employee):
    from app.models.enums import RiskLevel

    value = (employee.current_risk_level or "").lower()
    for level in RiskLevel:
        if level.value == value:
            return level
    return RiskLevel.MEDIUM


def create_rule(db: Session, data: dict, actor_id: Optional[int] = None) -> AlertRule:
    scope = data.get("scope", TargetScope.ORGANISATION)
    if scope == TargetScope.DEPARTMENT and not data.get("department_id"):
        raise BusinessRuleError("A department-scoped rule needs a department_id.")
    if scope == TargetScope.EMPLOYEE and not data.get("employee_id"):
        raise BusinessRuleError("An employee-scoped rule needs an employee_id.")
    if data.get("operator") == RuleOperator.BETWEEN and data.get("secondary_threshold") is None:
        raise BusinessRuleError("A 'between' rule needs a secondary_threshold.")

    rule = AlertRule(**data, created_by_id=actor_id)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule
