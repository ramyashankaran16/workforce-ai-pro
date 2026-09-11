"""Attendance endpoints."""

from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import (
    RequirePermissions,
    get_current_employee,
    get_current_user,
)
from app.core.pagination import Page, PaginationParams, paginate
from app.models.attendance import Attendance, Holiday
from app.models.employee import Employee
from app.models.enums import AttendanceStatus, RegularizationStatus
from app.models.user import User
from app.schemas.attendance import (
    AttendanceManualCreate,
    AttendanceRead,
    AttendanceSummary,
    CheckInRequest,
    CheckOutRequest,
    HolidayCreate,
    HolidayRead,
    RegularizationDecision,
    RegularizationRequest,
)
from app.schemas.common import MessageResponse
from app.services import attendance_service, employee_service

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/check-in", response_model=AttendanceRead, summary="Clock in")
def check_in(
    payload: CheckInRequest,
    request: Request,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    """
    Late minutes are measured against the assigned shift's grace period. For a
    night shift, the record is filed under the date the shift started.
    """
    return attendance_service.check_in(
        db,
        employee.id,
        location=payload.location,
        is_remote=payload.is_remote,
        ip=_client_ip(request),
    )


@router.post("/check-out", response_model=AttendanceRead, summary="Clock out")
def check_out(
    payload: CheckOutRequest,
    request: Request,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    return attendance_service.check_out(
        db, employee.id, remarks=payload.remarks, ip=_client_ip(request)
    )


@router.get("/me", response_model=Page[AttendanceRead], summary="Own attendance")
def my_attendance(
    params: PaginationParams = Depends(),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    stmt = select(Attendance).where(Attendance.employee_id == employee.id)
    if start:
        stmt = stmt.where(Attendance.attendance_date >= start)
    if end:
        stmt = stmt.where(Attendance.attendance_date <= end)
    stmt = stmt.order_by(Attendance.attendance_date.desc())

    rows, total = paginate(db, stmt, params)
    return Page[AttendanceRead].create(
        [AttendanceRead.model_validate(r) for r in rows], total, params
    )


@router.get("", response_model=Page[AttendanceRead], summary="List attendance (scoped)")
def list_attendance(
    params: PaginationParams = Depends(),
    employee_id: Optional[int] = Query(None),
    department_id: Optional[int] = Query(None),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    status_filter: Optional[AttendanceStatus] = Query(None, alias="status"),
    current_user: User = Depends(RequirePermissions("attendance:read_team", "attendance:read_all", require_all=False)),
    db: Session = Depends(get_db),
):
    """Managers see their own team; HR and admin see everyone."""
    visible = employee_service.scope_query(db, select(Employee.id), current_user)
    visible_ids = [row for row in db.execute(visible).scalars().all()]

    stmt = select(Attendance).where(Attendance.employee_id.in_(visible_ids))
    if employee_id is not None:
        stmt = stmt.where(Attendance.employee_id == employee_id)
    if department_id is not None:
        stmt = stmt.join(Employee).where(Employee.department_id == department_id)
    if start:
        stmt = stmt.where(Attendance.attendance_date >= start)
    if end:
        stmt = stmt.where(Attendance.attendance_date <= end)
    if status_filter:
        stmt = stmt.where(Attendance.status == status_filter)

    stmt = stmt.order_by(Attendance.attendance_date.desc(), Attendance.employee_id)
    rows, total = paginate(db, stmt, params)
    return Page[AttendanceRead].create(
        [AttendanceRead.model_validate(r) for r in rows], total, params
    )


@router.get(
    "/summary/{employee_id}",
    response_model=AttendanceSummary,
    summary="Monthly summary for one employee",
)
def summary(
    employee_id: int,
    start: date = Query(..., description="Period start"),
    end: date = Query(..., description="Period end"),
    current_user: User = Depends(RequirePermissions("attendance:read")),
    db: Session = Depends(get_db),
):
    employee = employee_service.get_employee(db, employee_id)
    employee_service.assert_can_access(db, current_user, employee)
    return attendance_service.monthly_summary(db, employee_id, start, end)


@router.post(
    "/regularize",
    response_model=AttendanceRead,
    summary="Request a correction for a past date",
)
def request_regularization(
    payload: RegularizationRequest,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    return attendance_service.request_regularization(
        db, employee.id, payload.model_dump()
    )


@router.get(
    "/regularizations/pending",
    response_model=Page[AttendanceRead],
    summary="Pending regularisation queue",
)
def pending_regularizations(
    params: PaginationParams = Depends(),
    current_user: User = Depends(RequirePermissions("attendance:manage")),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Attendance)
        .where(Attendance.regularization_status == RegularizationStatus.PENDING)
        .order_by(Attendance.attendance_date.desc())
    )
    rows, total = paginate(db, stmt, params)
    return Page[AttendanceRead].create(
        [AttendanceRead.model_validate(r) for r in rows], total, params
    )


@router.post(
    "/{attendance_id}/regularization",
    response_model=AttendanceRead,
    summary="Approve or reject a regularisation",
)
def decide_regularization(
    attendance_id: int,
    payload: RegularizationDecision,
    current_user: User = Depends(RequirePermissions("attendance:manage")),
    db: Session = Depends(get_db),
):
    return attendance_service.decide_regularization(
        db, attendance_id, payload.approve, current_user.id, payload.remarks
    )


@router.post(
    "/manual",
    response_model=AttendanceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create or correct a record directly (HR)",
)
def manual_entry(
    payload: AttendanceManualCreate,
    current_user: User = Depends(RequirePermissions("attendance:manage")),
    db: Session = Depends(get_db),
):
    return attendance_service.upsert_manual(
        db, payload.model_dump(), actor_id=current_user.id
    )


@router.post(
    "/run-daily-marking",
    response_model=MessageResponse,
    summary="Close open records and stamp statuses for a date",
)
def run_daily_marking(
    on: date = Query(..., description="Date to process"),
    _: User = Depends(RequirePermissions("attendance:manage")),
    db: Session = Depends(get_db),
):
    """
    Normally driven by the nightly scheduler; exposed so it can be run on
    demand and demonstrated.
    """
    closed = attendance_service.close_forgotten_checkouts(db, on)
    counts = attendance_service.mark_daily_attendance(db, on)
    return MessageResponse(
        message=f"Processed {on}: {closed} record(s) auto-closed.",
        data=counts,
    )


# ------------------------------------------------------------------- holidays
@router.get("/holidays", response_model=List[HolidayRead], summary="Holiday calendar")
def list_holidays(
    year: Optional[int] = Query(None),
    _: User = Depends(RequirePermissions("attendance:read")),
    db: Session = Depends(get_db),
):
    stmt = select(Holiday)
    if year:
        stmt = stmt.where(
            Holiday.holiday_date >= date(year, 1, 1),
            Holiday.holiday_date <= date(year, 12, 31),
        )
    return db.execute(stmt.order_by(Holiday.holiday_date)).scalars().all()


@router.post(
    "/holidays",
    response_model=HolidayRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a holiday",
)
def create_holiday(
    payload: HolidayCreate,
    _: User = Depends(RequirePermissions("attendance:manage")),
    db: Session = Depends(get_db),
):
    holiday = Holiday(**payload.model_dump())
    db.add(holiday)
    db.commit()
    db.refresh(holiday)
    return holiday
