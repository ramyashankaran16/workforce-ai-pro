"""Audit log and activity tracking endpoints."""

from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PaginationParams, paginate
from app.models.audit import ActivityLog, AuditLog, LoginHistory
from app.models.enums import AuditAction
from app.models.user import User
from app.schemas.audit import (
    ActivityLogRead,
    AuditLogDetail,
    AuditLogRead,
    AuditSummary,
    LoginHistoryRead,
    SuspiciousLogin,
)
from app.services import audit_service

router = APIRouter(prefix="/audit", tags=["Audit & Activity"])


@router.get("/logs", response_model=Page[AuditLogRead], summary="Filter audit entries")
def list_logs(
    params: PaginationParams = Depends(),
    user_id: Optional[int] = Query(None),
    action: Optional[AuditAction] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[int] = Query(None),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    successful_only: Optional[bool] = Query(None),
    _: User = Depends(RequirePermissions("audit:read")),
    db: Session = Depends(get_db),
):
    """Append-only by design: there is no update or delete route here."""
    stmt = select(AuditLog)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if start:
        stmt = stmt.where(
            AuditLog.created_at >= datetime.combine(start, datetime.min.time())
        )
    if end:
        stmt = stmt.where(
            AuditLog.created_at <= datetime.combine(end, datetime.max.time())
        )
    if successful_only is not None:
        stmt = stmt.where(AuditLog.is_successful.is_(successful_only))

    stmt = stmt.order_by(AuditLog.created_at.desc())
    rows, total = paginate(db, stmt, params)
    return Page[AuditLogRead].create(
        [AuditLogRead.model_validate(r) for r in rows], total, params
    )


@router.get(
    "/logs/{log_id}", response_model=AuditLogDetail, summary="Old vs new values"
)
def get_log(
    log_id: int,
    _: User = Depends(RequirePermissions("audit:read")),
    db: Session = Depends(get_db),
):
    """Sensitive fields such as passwords and bank details are stored redacted."""
    entry = db.get(AuditLog, log_id)
    if entry is None:
        raise NotFoundError("Audit entry not found.")
    return entry


@router.get(
    "/trail/{entity_type}/{entity_id}",
    response_model=List[AuditLogDetail],
    summary="Full history for one record",
)
def entity_trail(
    entity_type: str,
    entity_id: int,
    _: User = Depends(RequirePermissions("audit:read")),
    db: Session = Depends(get_db),
):
    return audit_service.entity_trail(db, entity_type, entity_id)


@router.get(
    "/activity", response_model=Page[ActivityLogRead], summary="Activity feed"
)
def activity(
    params: PaginationParams = Depends(),
    module: Optional[str] = Query(None),
    _: User = Depends(RequirePermissions("audit:read")),
    db: Session = Depends(get_db),
):
    stmt = select(ActivityLog)
    if module:
        stmt = stmt.where(ActivityLog.module == module)
    stmt = stmt.order_by(ActivityLog.created_at.desc())

    rows, total = paginate(db, stmt, params)
    return Page[ActivityLogRead].create(
        [ActivityLogRead.model_validate(r) for r in rows], total, params
    )


@router.get(
    "/login-history",
    response_model=Page[LoginHistoryRead],
    summary="Authentication attempts",
)
def login_history(
    params: PaginationParams = Depends(),
    successful_only: Optional[bool] = Query(None),
    email: Optional[str] = Query(None),
    _: User = Depends(RequirePermissions("audit:read")),
    db: Session = Depends(get_db),
):
    stmt = select(LoginHistory)
    if successful_only is not None:
        stmt = stmt.where(LoginHistory.is_successful.is_(successful_only))
    if email:
        stmt = stmt.where(LoginHistory.email_attempted.ilike(f"%{email}%"))
    stmt = stmt.order_by(LoginHistory.logged_in_at.desc())

    rows, total = paginate(db, stmt, params)
    return Page[LoginHistoryRead].create(
        [LoginHistoryRead.model_validate(r) for r in rows], total, params
    )


@router.get("/summary", response_model=AuditSummary, summary="Activity summary")
def summary(
    days: int = Query(30, ge=1, le=365),
    _: User = Depends(RequirePermissions("audit:read")),
    db: Session = Depends(get_db),
):
    return audit_service.summary(db, days)


@router.get(
    "/suspicious-logins",
    response_model=List[SuspiciousLogin],
    summary="Repeated authentication failures",
)
def suspicious(
    threshold: int = Query(5, ge=2, le=50),
    hours: int = Query(24, ge=1, le=168),
    _: User = Depends(RequirePermissions("audit:read")),
    db: Session = Depends(get_db),
):
    """
    Account lockout stops repeated attempts against one account; this surfaces
    the pattern that lockout alone does not, such as one password tried across
    many addresses.
    """
    return audit_service.suspicious_logins(db, threshold, hours)
