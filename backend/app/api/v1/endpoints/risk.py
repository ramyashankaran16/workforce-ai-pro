"""Employee risk monitoring endpoints."""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PaginationParams, paginate
from app.models.employee import Employee
from app.models.enums import AlertStatus, RiskLevel
from app.models.risk import RiskAlert, RiskScore
from app.models.user import User
from app.schemas.risk import (
    AlertResolve,
    EvaluateResult,
    HeatmapEntry,
    RiskAlertRead,
    RiskScoreDetail,
    RiskScoreRead,
)
from app.services import employee_service, risk_service

router = APIRouter(prefix="/risk", tags=["Risk Monitoring"])


@router.get("/scores", response_model=Page[RiskScoreRead], summary="List risk scores")
def list_scores(
    params: PaginationParams = Depends(),
    risk_level: Optional[RiskLevel] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=100),
    current_user: User = Depends(
        RequirePermissions("risk:read_team", "risk:read_all", require_all=False)
    ),
    db: Session = Depends(get_db),
):
    visible_ids = db.execute(
        employee_service.scope_query(db, select(Employee.id), current_user)
    ).scalars().all()

    stmt = select(RiskScore).where(RiskScore.employee_id.in_(visible_ids))
    if risk_level:
        stmt = stmt.where(RiskScore.risk_level == risk_level)
    if min_score is not None:
        stmt = stmt.where(RiskScore.overall_score >= min_score)
    stmt = stmt.order_by(RiskScore.overall_score.desc())

    rows, total = paginate(db, stmt, params)
    return Page[RiskScoreRead].create(
        [RiskScoreRead.model_validate(r) for r in rows], total, params
    )


@router.get(
    "/employee/{employee_id}",
    response_model=RiskScoreDetail,
    summary="Latest score with its sub-scores and factors",
)
def employee_risk(
    employee_id: int,
    current_user: User = Depends(
        RequirePermissions("risk:read_team", "risk:read_all", require_all=False)
    ),
    db: Session = Depends(get_db),
):
    """
    Every sub-score is shown with the weight applied to it, so a number on a
    dashboard can always be taken apart.
    """
    employee = employee_service.get_employee(db, employee_id)
    employee_service.assert_can_access(db, current_user, employee)

    score = db.execute(
        select(RiskScore)
        .options(selectinload(RiskScore.factors))
        .where(RiskScore.employee_id == employee_id)
        .order_by(RiskScore.evaluation_date.desc(), RiskScore.id.desc())
    ).scalars().first()

    if score is None:
        raise NotFoundError(
            "No risk score yet for this employee. Run POST /risk/evaluate first."
        )

    payload = {c.name: getattr(score, c.name) for c in score.__table__.columns}
    payload.update(
        {
            "factors": score.factors,
            "employee_code": employee.employee_code,
            "employee_name": employee.full_name,
        }
    )
    return payload


@router.get(
    "/employee/{employee_id}/history",
    response_model=List[RiskScoreRead],
    summary="Score history",
)
def risk_history(
    employee_id: int,
    current_user: User = Depends(
        RequirePermissions("risk:read_team", "risk:read_all", require_all=False)
    ),
    db: Session = Depends(get_db),
):
    employee = employee_service.get_employee(db, employee_id)
    employee_service.assert_can_access(db, current_user, employee)
    return (
        db.execute(
            select(RiskScore)
            .where(RiskScore.employee_id == employee_id)
            # id breaks the tie: several evaluations can share a date, and
            # without it the newest one is not reliably first
            .order_by(RiskScore.evaluation_date.desc(), RiskScore.id.desc())
        )
        .scalars()
        .all()
    )


@router.post(
    "/evaluate", response_model=EvaluateResult, summary="Recompute composite scores"
)
def evaluate(
    employee_id: Optional[int] = Query(
        None, description="Score one employee; omit for everyone"
    ),
    _: User = Depends(RequirePermissions("risk:manage")),
    db: Session = Depends(get_db),
):
    """
    Blends the model probability with compensation, engagement, workload,
    attendance, performance, tenure and leave-pattern sub-scores.

    When no model is deployed the ML weight is redistributed across the
    remaining components rather than scored as zero, which would quietly halve
    everyone's risk.
    """
    if employee_id is not None:
        employee = employee_service.get_employee(db, employee_id)
        record = risk_service.evaluate_employee(db, employee)
        return {
            "evaluated": 1,
            "critical": int(record.risk_level == RiskLevel.CRITICAL),
            "high": int(record.risk_level == RiskLevel.HIGH),
            "medium": int(record.risk_level == RiskLevel.MEDIUM),
            "low": int(record.risk_level == RiskLevel.LOW),
        }
    return risk_service.evaluate_all(db)


@router.get("/heatmap", response_model=List[HeatmapEntry], summary="Risk by department")
def heatmap(
    _: User = Depends(RequirePermissions("risk:read_all")),
    db: Session = Depends(get_db),
):
    return risk_service.department_heatmap(db)


# ------------------------------------------------------------------------ alerts
@router.get("/alerts", response_model=Page[RiskAlertRead], summary="Alert queue")
def list_alerts(
    params: PaginationParams = Depends(),
    status_filter: Optional[AlertStatus] = Query(None, alias="status"),
    risk_level: Optional[RiskLevel] = Query(None),
    assigned_to_me: bool = Query(False),
    current_user: User = Depends(
        RequirePermissions("risk:read_team", "risk:read_all", require_all=False)
    ),
    db: Session = Depends(get_db),
):
    visible_ids = db.execute(
        employee_service.scope_query(db, select(Employee.id), current_user)
    ).scalars().all()

    stmt = select(RiskAlert).where(RiskAlert.employee_id.in_(visible_ids))
    if status_filter:
        stmt = stmt.where(RiskAlert.status == status_filter)
    if risk_level:
        stmt = stmt.where(RiskAlert.risk_level == risk_level)
    if assigned_to_me:
        stmt = stmt.where(RiskAlert.assigned_to_id == current_user.id)

    stmt = stmt.order_by(RiskAlert.created_at.desc())
    rows, total = paginate(db, stmt, params)
    return Page[RiskAlertRead].create(
        [RiskAlertRead.model_validate(r) for r in rows], total, params
    )


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=RiskAlertRead,
    summary="Acknowledge an alert",
)
def acknowledge_alert(
    alert_id: int,
    current_user: User = Depends(RequirePermissions("risk:manage")),
    db: Session = Depends(get_db),
):
    return risk_service.acknowledge(db, alert_id, current_user.id)


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=RiskAlertRead,
    summary="Resolve or dismiss an alert",
)
def resolve_alert(
    alert_id: int,
    payload: AlertResolve,
    current_user: User = Depends(RequirePermissions("risk:manage")),
    db: Session = Depends(get_db),
):
    return risk_service.resolve(
        db, alert_id, current_user.id, payload.notes, payload.dismiss
    )
