"""Smart alert engine endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PaginationParams, paginate
from app.models.alert_rule import AlertRule, AlertTrigger
from app.models.user import User
from app.schemas.alert_rule import (
    AlertRuleCreate,
    AlertRuleRead,
    AlertRuleUpdate,
    AlertTriggerRead,
    EvaluationResult,
)
from app.schemas.common import MessageResponse
from app.services import alert_engine

router = APIRouter(prefix="/alert-rules", tags=["Smart Alert Engine"])


@router.get("", response_model=Page[AlertRuleRead], summary="List rules")
def list_rules(
    params: PaginationParams = Depends(),
    is_active: Optional[bool] = Query(None),
    _: User = Depends(RequirePermissions("alert_rule:manage")),
    db: Session = Depends(get_db),
):
    stmt = select(AlertRule)
    if is_active is not None:
        stmt = stmt.where(AlertRule.is_active.is_(is_active))
    stmt = stmt.order_by(AlertRule.id.desc())

    rows, total = paginate(db, stmt, params)
    return Page[AlertRuleRead].create(
        [AlertRuleRead.model_validate(r) for r in rows], total, params
    )


@router.post(
    "",
    response_model=AlertRuleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a threshold rule",
)
def create_rule(
    payload: AlertRuleCreate,
    current_user: User = Depends(RequirePermissions("alert_rule:manage")),
    db: Session = Depends(get_db),
):
    """
    `cooldown_hours` is what keeps this from becoming a notification firehose:
    the same rule cannot re-fire for the same employee inside that window, and
    a rule with an already-open alert for someone is skipped entirely.
    """
    return alert_engine.create_rule(
        db, payload.model_dump(), actor_id=current_user.id
    )


@router.get("/{rule_id}", response_model=AlertRuleRead, summary="Get a rule")
def get_rule(
    rule_id: int,
    _: User = Depends(RequirePermissions("alert_rule:manage")),
    db: Session = Depends(get_db),
):
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise NotFoundError("Alert rule not found.")
    return rule


@router.patch("/{rule_id}", response_model=AlertRuleRead, summary="Update a rule")
def update_rule(
    rule_id: int,
    payload: AlertRuleUpdate,
    _: User = Depends(RequirePermissions("alert_rule:manage")),
    db: Session = Depends(get_db),
):
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise NotFoundError("Alert rule not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", response_model=MessageResponse, summary="Delete a rule")
def delete_rule(
    rule_id: int,
    _: User = Depends(RequirePermissions("alert_rule:manage")),
    db: Session = Depends(get_db),
):
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise NotFoundError("Alert rule not found.")
    db.delete(rule)
    db.commit()
    return MessageResponse(message="Alert rule deleted.")


@router.post(
    "/evaluate",
    response_model=EvaluationResult,
    summary="Run the rules now",
)
def evaluate(
    rule_id: Optional[int] = Query(None, description="Run one rule; omit for all active"),
    notify: bool = Query(True, description="Create in-app notifications"),
    _: User = Depends(RequirePermissions("alert_rule:manage")),
    db: Session = Depends(get_db),
):
    """
    Normally driven by the nightly scheduler. The `suppressed` count in the
    response shows how many matches were withheld by cooldown or an existing
    open alert.
    """
    return alert_engine.evaluate_rules(db, rule_id=rule_id, notify=notify)


@router.get(
    "/{rule_id}/triggers",
    response_model=Page[AlertTriggerRead],
    summary="Trigger history for a rule",
)
def rule_triggers(
    rule_id: int,
    params: PaginationParams = Depends(),
    _: User = Depends(RequirePermissions("alert_rule:manage")),
    db: Session = Depends(get_db),
):
    stmt = (
        select(AlertTrigger)
        .where(AlertTrigger.rule_id == rule_id)
        .order_by(AlertTrigger.created_at.desc())
    )
    rows, total = paginate(db, stmt, params)
    return Page[AlertTriggerRead].create(
        [AlertTriggerRead.model_validate(r) for r in rows], total, params
    )
