"""Real-time workforce monitoring endpoints."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.models.attendance import Attendance
from app.models.audit import ActivityLog
from app.models.employee import Employee
from app.models.user import User
from app.services import analytics_service

router = APIRouter(prefix="/monitoring", tags=["Real-Time Monitoring"])


@router.get("/live", summary="Current workforce snapshot")
def live(
    _: User = Depends(RequirePermissions("dashboard:read")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Polling endpoint. Intended to be called on a short interval by the
    dashboard.

    Aggregate figures like headcount do not change second to second, so
    polling is the right tool here; the WebSocket channel is reserved for
    events that genuinely need to arrive immediately, such as a critical risk
    alert or a chat message.
    """
    return analytics_service.live_snapshot(db)


@router.get("/presence", summary="Who is checked in right now")
def presence(
    _: User = Depends(RequirePermissions("attendance:read_all")),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    from datetime import date

    rows = db.execute(
        select(Attendance, Employee)
        .join(Employee, Employee.id == Attendance.employee_id)
        .where(
            Attendance.attendance_date == date.today(),
            Attendance.check_in.isnot(None),
            Attendance.check_out.is_(None),
        )
        .order_by(Attendance.check_in)
    ).all()

    return [
        {
            "employee_id": employee.id,
            "employee_code": employee.employee_code,
            "full_name": employee.full_name,
            "checked_in_at": record.check_in,
            "is_remote": record.is_remote,
            "location": record.check_in_location,
        }
        for record, employee in rows
    ]


@router.get("/activity", summary="Recent activity feed")
def activity(
    limit: int = Query(25, ge=1, le=100),
    _: User = Depends(RequirePermissions("dashboard:read")),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    rows = (
        db.execute(
            select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": row.id,
            "activity_type": row.activity_type,
            "title": row.title,
            "description": row.description,
            "module": row.module,
            "created_at": row.created_at,
        }
        for row in rows
    ]
