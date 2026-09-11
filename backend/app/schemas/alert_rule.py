"""Alert rule schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    NotificationChannel,
    Priority,
    RuleOperator,
    RuleTargetMetric,
    TargetScope,
)
from app.schemas.common import ORMBase


class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    description: Optional[str] = None
    metric: RuleTargetMetric
    operator: RuleOperator
    threshold_value: float
    secondary_threshold: Optional[float] = None

    scope: TargetScope = TargetScope.ORGANISATION
    department_id: Optional[int] = None
    employee_id: Optional[int] = None

    priority: Priority = Priority.MEDIUM
    channel: NotificationChannel = NotificationChannel.IN_APP
    notify_roles: Dict[str, Any] = Field(
        default_factory=lambda: {"roles": ["hr"]},
        description='Which roles to notify, e.g. {"roles": ["hr", "manager"]}',
    )
    message_template: Optional[str] = Field(
        None,
        description=(
            "Placeholders: {employee} {employee_code} {rule} {metric} "
            "{value} {operator} {threshold}"
        ),
    )
    cooldown_hours: int = Field(
        24, ge=0, le=720,
        description="Minimum gap before the same rule can re-fire for the same person.",
    )

    @model_validator(mode="after")
    def check_between(self):
        if self.operator == RuleOperator.BETWEEN and self.secondary_threshold is None:
            raise ValueError("A 'between' rule needs a secondary_threshold.")
        if (
            self.secondary_threshold is not None
            and self.secondary_threshold < self.threshold_value
        ):
            raise ValueError("secondary_threshold must be at or above threshold_value.")
        return self


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=150)
    description: Optional[str] = None
    threshold_value: Optional[float] = None
    secondary_threshold: Optional[float] = None
    priority: Optional[Priority] = None
    channel: Optional[NotificationChannel] = None
    notify_roles: Optional[Dict[str, Any]] = None
    message_template: Optional[str] = None
    cooldown_hours: Optional[int] = Field(None, ge=0, le=720)
    is_active: Optional[bool] = None


class AlertRuleRead(ORMBase):
    id: int
    name: str
    description: Optional[str] = None
    metric: RuleTargetMetric
    operator: RuleOperator
    threshold_value: float
    secondary_threshold: Optional[float] = None
    scope: TargetScope
    department_id: Optional[int] = None
    employee_id: Optional[int] = None
    priority: Priority
    channel: NotificationChannel
    notify_roles: Optional[Dict[str, Any]] = None
    message_template: Optional[str] = None
    cooldown_hours: int
    is_active: bool
    trigger_count: int
    last_triggered_at: Optional[datetime] = None


class AlertTriggerRead(ORMBase):
    id: int
    rule_id: int
    employee_id: Optional[int] = None
    department_id: Optional[int] = None
    metric_value: float
    threshold_value: float
    message: Optional[str] = None
    notifications_sent: int
    created_at: datetime


class EvaluationResult(BaseModel):
    rules_evaluated: int
    triggers: int
    alerts_created: int
    notifications_sent: int
    suppressed: int = Field(
        0, description="Blocked by cooldown or an already-open alert."
    )
