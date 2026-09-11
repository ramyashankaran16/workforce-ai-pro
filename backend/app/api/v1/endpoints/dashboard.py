"""Dashboard and workforce analytics endpoints."""

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions, get_current_user
from app.models.user import User
from app.services import analytics_service, employee_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("", summary="Role-scoped dashboard")
def dashboard(
    current_user: User = Depends(RequirePermissions("dashboard:read")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    One endpoint for all four roles rather than four endpoints.

    The tiles overlap heavily; what changes is the scope of the data and which
    sections appear. An employee gets their own section only; a manager gets a
    team block scoped to their reportees; HR and admin get the organisation
    plus the risk distribution.
    """
    employee = employee_service.get_by_user(db, current_user.id)
    return analytics_service.dashboard_for(db, current_user, employee)


@router.get("/headcount", summary="Headcount breakdown")
def headcount(
    _: User = Depends(RequirePermissions("analytics:read_all")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return analytics_service.headcount_breakdown(db)
