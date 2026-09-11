"""
Attendance: check-in/out calculation, regularisation and summaries.

Two rules drive most of this module:

1. An attendance row belongs to the date the shift *started*. A night shift
   running 22:00 Monday to 06:00 Tuesday is one Monday record, not two.
2. worked_hours is derived, never supplied by the client. A forgotten check-out
   leaves the record open until the nightly job closes it.
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models.attendance import Attendance, Holiday, Shift
from app.models.employee import Employee
from app.models.enums import (
    AttendanceStatus,
    LeaveStatus,
    RegularizationStatus,
)
from app.models.leave import LeaveRequest
from app.services import shift_service
from app.utils.date_utils import utcnow

WEEKEND_DAYS = {5, 6}  # Saturday, Sunday


# ------------------------------------------------------------------ calendars
def holiday_dates(db: Session, start: date, end: date) -> Dict[date, str]:
    rows = (
        db.execute(
            select(Holiday).where(
                Holiday.holiday_date >= start,
                Holiday.holiday_date <= end,
                Holiday.is_optional.is_(False),
            )
        )
        .scalars()
        .all()
    )
    return {h.holiday_date: h.name for h in rows}


def is_working_day(day: date, holidays: Dict[date, str]) -> bool:
    return day.weekday() not in WEEKEND_DAYS and day not in holidays


def working_days_between(db: Session, start: date, end: date) -> int:
    holidays = holiday_dates(db, start, end)
    count = 0
    cursor = start
    while cursor <= end:
        if is_working_day(cursor, holidays):
            count += 1
        cursor += timedelta(days=1)
    return count


# ------------------------------------------------------------- shift boundary
def attendance_date_for(shift: Optional[Shift], moment: datetime) -> date:
    """
    Which calendar date a check-in belongs to.

    For a night shift, a check-in in the small hours belongs to the *previous*
    day's record -- someone clocking in at 00:30 for a 22:00 shift started
    yesterday.
    """
    if shift and shift.is_night_shift and moment.time() < shift.end_time:
        return (moment - timedelta(days=1)).date()
    return moment.date()


def _shift_start_dt(shift: Shift, on: date) -> datetime:
    return datetime.combine(on, shift.start_time)


def _shift_end_dt(shift: Shift, on: date) -> datetime:
    end = datetime.combine(on, shift.end_time)
    if shift.is_night_shift:
        end += timedelta(days=1)
    return end


# ------------------------------------------------------------------ check in
def check_in(
    db: Session,
    employee_id: int,
    location: Optional[str] = None,
    is_remote: bool = False,
    ip: Optional[str] = None,
    moment: Optional[datetime] = None,
) -> Attendance:
    employee = db.get(Employee, employee_id)
    if employee is None or employee.is_deleted:
        raise NotFoundError("Employee not found.")

    now = moment or utcnow()
    shift = shift_service.shift_for_employee(db, employee_id, now.date())
    day = attendance_date_for(shift, now)

    record = db.execute(
        select(Attendance).where(
            Attendance.employee_id == employee_id,
            Attendance.attendance_date == day,
        )
    ).scalar_one_or_none()

    if record and record.check_in:
        raise BusinessRuleError(f"Already checked in for {day}.")

    late_minutes = 0
    status = AttendanceStatus.PRESENT
    if shift:
        expected = _shift_start_dt(shift, day)
        delta = (now - expected).total_seconds() / 60
        if delta > shift.grace_period_minutes:
            late_minutes = int(delta)
            status = AttendanceStatus.LATE

    if is_remote:
        status = AttendanceStatus.WORK_FROM_HOME

    if record is None:
        record = Attendance(employee_id=employee_id, attendance_date=day)
        db.add(record)

    record.shift_id = shift.id if shift else None
    record.check_in = now
    record.check_in_ip = ip
    record.check_in_location = location
    record.is_remote = is_remote
    record.late_minutes = late_minutes
    record.status = status

    db.commit()
    db.refresh(record)
    return record


# ----------------------------------------------------------------- check out
def check_out(
    db: Session,
    employee_id: int,
    remarks: Optional[str] = None,
    ip: Optional[str] = None,
    moment: Optional[datetime] = None,
) -> Attendance:
    now = moment or utcnow()
    shift = shift_service.shift_for_employee(db, employee_id, now.date())
    day = attendance_date_for(shift, now)

    record = db.execute(
        select(Attendance).where(
            Attendance.employee_id == employee_id,
            Attendance.attendance_date == day,
        )
    ).scalar_one_or_none()

    if record is None or record.check_in is None:
        raise BusinessRuleError(f"No check-in found for {day}.")
    if record.check_out:
        raise BusinessRuleError(f"Already checked out for {day}.")
    if now <= record.check_in:
        raise BusinessRuleError("Check-out must be after check-in.")

    record.check_out = now
    record.check_out_ip = ip
    if remarks:
        record.remarks = remarks

    _recompute(db, record, shift)
    db.commit()
    db.refresh(record)
    return record


def _recompute(db: Session, record: Attendance, shift: Optional[Shift]) -> None:
    """Derive worked hours, overtime, early exit and the resulting status."""
    if not (record.check_in and record.check_out):
        return

    gross_minutes = (record.check_out - record.check_in).total_seconds() / 60
    break_minutes = shift.break_minutes if shift else 0
    worked = max(gross_minutes - break_minutes, 0) / 60
    record.worked_hours = round(worked, 2)

    if shift:
        expected_end = _shift_end_dt(shift, record.attendance_date)
        early = (expected_end - record.check_out).total_seconds() / 60
        record.early_exit_minutes = int(early) if early > 0 else 0
        record.overtime_hours = round(max(worked - shift.working_hours, 0), 2)

        if worked < shift.half_day_threshold_hours:
            record.status = AttendanceStatus.HALF_DAY
        elif record.is_remote:
            record.status = AttendanceStatus.WORK_FROM_HOME
        elif record.late_minutes > 0:
            record.status = AttendanceStatus.LATE
        else:
            record.status = AttendanceStatus.PRESENT
    else:
        record.overtime_hours = 0.0
        record.early_exit_minutes = 0
        if not record.is_remote:
            record.status = AttendanceStatus.PRESENT


# ------------------------------------------------------------ regularisation
def request_regularization(
    db: Session, employee_id: int, data: dict
) -> Attendance:
    day = data["attendance_date"]
    if day > date.today():
        raise BusinessRuleError("Cannot regularise a future date.")

    record = db.execute(
        select(Attendance).where(
            Attendance.employee_id == employee_id,
            Attendance.attendance_date == day,
        )
    ).scalar_one_or_none()

    if record is None:
        record = Attendance(
            employee_id=employee_id,
            attendance_date=day,
            status=AttendanceStatus.ABSENT,
        )
        db.add(record)

    if record.regularization_status == RegularizationStatus.PENDING:
        raise BusinessRuleError("A regularisation is already pending for that date.")

    record.regularization_status = RegularizationStatus.PENDING
    record.regularization_reason = data["reason"]
    if data.get("check_in"):
        record.check_in = data["check_in"]
    if data.get("check_out"):
        record.check_out = data["check_out"]

    db.commit()
    db.refresh(record)
    return record


def decide_regularization(
    db: Session, attendance_id: int, approve: bool, approver_id: int,
    remarks: Optional[str] = None,
) -> Attendance:
    record = db.get(Attendance, attendance_id)
    if record is None:
        raise NotFoundError("Attendance record not found.")
    if record.regularization_status != RegularizationStatus.PENDING:
        raise BusinessRuleError("No pending regularisation on that record.")

    record.approved_by_id = approver_id
    if remarks:
        record.remarks = remarks

    if approve:
        record.regularization_status = RegularizationStatus.APPROVED
        shift = db.get(Shift, record.shift_id) if record.shift_id else None
        if record.check_in and record.check_out:
            _recompute(db, record, shift)
        else:
            record.status = AttendanceStatus.PRESENT
    else:
        record.regularization_status = RegularizationStatus.REJECTED

    db.commit()
    db.refresh(record)
    return record


# ---------------------------------------------------------------- manual entry
def upsert_manual(db: Session, data: dict, actor_id: Optional[int] = None) -> Attendance:
    employee = db.get(Employee, data["employee_id"])
    if employee is None or employee.is_deleted:
        raise NotFoundError("Employee not found.")

    record = db.execute(
        select(Attendance).where(
            Attendance.employee_id == data["employee_id"],
            Attendance.attendance_date == data["attendance_date"],
        )
    ).scalar_one_or_none()

    if record is None:
        record = Attendance(
            employee_id=data["employee_id"],
            attendance_date=data["attendance_date"],
        )
        db.add(record)

    record.check_in = data.get("check_in")
    record.check_out = data.get("check_out")
    record.status = data["status"]
    record.is_remote = data.get("is_remote", False)
    record.remarks = data.get("remarks")
    record.approved_by_id = actor_id

    shift = shift_service.shift_for_employee(
        db, data["employee_id"], data["attendance_date"]
    )
    record.shift_id = shift.id if shift else None
    if record.check_in and record.check_out:
        _recompute(db, record, shift)
        record.status = data["status"]  # explicit status wins over derivation

    db.commit()
    db.refresh(record)
    return record


# ----------------------------------------------------------- scheduled jobs
def close_forgotten_checkouts(db: Session, on: date) -> int:
    """
    Close records with a check-in but no check-out.

    Credits hours up to the shift end rather than zero -- the person did work.
    The record is flagged so HR can see it was auto-closed.
    """
    open_records = (
        db.execute(
            select(Attendance).where(
                Attendance.attendance_date == on,
                Attendance.check_in.isnot(None),
                Attendance.check_out.is_(None),
            )
        )
        .scalars()
        .all()
    )

    for record in open_records:
        shift = db.get(Shift, record.shift_id) if record.shift_id else None
        if shift:
            record.check_out = _shift_end_dt(shift, record.attendance_date)
        else:
            record.check_out = record.check_in + timedelta(hours=8)
        _recompute(db, record, shift)
        record.remarks = ((record.remarks or "") + " [auto-closed: no check-out]").strip()
        record.regularization_status = RegularizationStatus.NOT_REQUESTED

    db.commit()
    return len(open_records)


def mark_daily_attendance(db: Session, on: date) -> Dict[str, int]:
    """
    Stamp a status on every active employee for a date.

    Runs after close_forgotten_checkouts. Anyone without a record gets
    weekend, holiday, on-leave or absent as appropriate.
    """
    holidays = holiday_dates(db, on, on)
    employees = (
        db.execute(
            select(Employee).where(
                Employee.is_deleted.is_(False),
                Employee.date_of_joining <= on,
                or_(Employee.date_of_exit.is_(None), Employee.date_of_exit >= on),
            )
        )
        .scalars()
        .all()
    )

    existing = {
        row.employee_id
        for row in db.execute(
            select(Attendance).where(Attendance.attendance_date == on)
        ).scalars().all()
    }

    on_leave = {
        row.employee_id
        for row in db.execute(
            select(LeaveRequest).where(
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.start_date <= on,
                LeaveRequest.end_date >= on,
            )
        ).scalars().all()
    }

    counts = {"weekend": 0, "holiday": 0, "on_leave": 0, "absent": 0}

    for employee in employees:
        if employee.id in existing:
            continue

        if on in holidays:
            status = AttendanceStatus.HOLIDAY
            counts["holiday"] += 1
        elif on.weekday() in WEEKEND_DAYS:
            status = AttendanceStatus.WEEKEND
            counts["weekend"] += 1
        elif employee.id in on_leave:
            status = AttendanceStatus.ON_LEAVE
            counts["on_leave"] += 1
        else:
            status = AttendanceStatus.ABSENT
            counts["absent"] += 1

        db.add(
            Attendance(
                employee_id=employee.id,
                attendance_date=on,
                status=status,
            )
        )

    db.commit()
    return counts


# -------------------------------------------------------------------- summary
def monthly_summary(
    db: Session, employee_id: int, start: date, end: date
) -> dict:
    employee = db.get(Employee, employee_id)
    if employee is None or employee.is_deleted:
        raise NotFoundError("Employee not found.")

    records = (
        db.execute(
            select(Attendance).where(
                Attendance.employee_id == employee_id,
                Attendance.attendance_date >= start,
                Attendance.attendance_date <= end,
            )
        )
        .scalars()
        .all()
    )

    working_days = working_days_between(db, start, end)
    present = sum(
        1
        for r in records
        if r.status
        in {
            AttendanceStatus.PRESENT,
            AttendanceStatus.LATE,
            AttendanceStatus.WORK_FROM_HOME,
        }
    )
    half_days = sum(1 for r in records if r.status == AttendanceStatus.HALF_DAY)
    leave_days = sum(1 for r in records if r.status == AttendanceStatus.ON_LEAVE)
    absent_days = sum(1 for r in records if r.status == AttendanceStatus.ABSENT)

    present_total = present + (half_days * 0.5)

    return {
        "employee_id": employee.id,
        "employee_code": employee.employee_code,
        "full_name": employee.full_name,
        "period_start": start,
        "period_end": end,
        "working_days": working_days,
        "present_days": present_total,
        "absent_days": float(absent_days),
        "leave_days": float(leave_days),
        "half_days": half_days,
        "late_count": sum(1 for r in records if r.late_minutes > 0),
        "total_worked_hours": round(sum(r.worked_hours for r in records), 2),
        "total_overtime_hours": round(sum(r.overtime_hours for r in records), 2),
        "attendance_percent": (
            round((present_total / working_days) * 100, 2) if working_days else 0.0
        ),
    }
