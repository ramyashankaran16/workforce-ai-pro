"""Shift templates, assignment overlap validation and roster generation."""

from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, DuplicateError, NotFoundError
from app.models.attendance import Shift, ShiftAssignment
from app.models.employee import Employee


def compute_working_hours(start, end, break_minutes: int) -> tuple:
    """
    Return (working_hours, is_night_shift).

    A shift whose end time is at or before its start time rolls past midnight,
    so a day is added before taking the difference.
    """
    base = date(2000, 1, 1)
    start_dt = datetime.combine(base, start)
    end_dt = datetime.combine(base, end)

    is_night = end <= start
    if is_night:
        end_dt += timedelta(days=1)

    total_minutes = (end_dt - start_dt).total_seconds() / 60 - break_minutes
    return round(max(total_minutes, 0) / 60, 2), is_night


def get_shift(db: Session, shift_id: int) -> Shift:
    shift = db.get(Shift, shift_id)
    if shift is None or shift.is_deleted:
        raise NotFoundError("Shift not found.")
    return shift


def create_shift(db: Session, data: dict) -> Shift:
    code = data["code"].upper().strip()
    if db.execute(select(Shift).where(Shift.code == code)).scalar_one_or_none():
        raise DuplicateError(f"Shift code '{code}' is already in use.")

    hours, is_night = compute_working_hours(
        data["start_time"], data["end_time"], data.get("break_minutes", 60)
    )
    shift = Shift(
        **{**data, "code": code}, working_hours=hours, is_night_shift=is_night
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


def update_shift(db: Session, shift_id: int, data: dict) -> Shift:
    shift = get_shift(db, shift_id)
    for field, value in data.items():
        setattr(shift, field, value)

    shift.working_hours, shift.is_night_shift = compute_working_hours(
        shift.start_time, shift.end_time, shift.break_minutes
    )
    db.commit()
    db.refresh(shift)
    return shift


def delete_shift(db: Session, shift_id: int) -> None:
    shift = get_shift(db, shift_id)
    active = db.execute(
        select(ShiftAssignment).where(
            ShiftAssignment.shift_id == shift_id,
            ShiftAssignment.is_active.is_(True),
        )
    ).scalars().first()
    if active:
        raise BusinessRuleError("Employees are still assigned to this shift.")
    shift.is_deleted = True
    shift.is_active = False
    db.commit()


def _overlaps(existing: ShiftAssignment, start: date, end: Optional[date]) -> bool:
    """Two open-ended ranges overlap unless one ends before the other begins."""
    existing_end = existing.end_date or date.max
    new_end = end or date.max
    return existing.start_date <= new_end and start <= existing_end


def assign_shift(
    db: Session,
    shift_id: int,
    employee_ids: List[int],
    start_date: date,
    end_date: Optional[date],
    actor_id: Optional[int] = None,
) -> List[ShiftAssignment]:
    """
    Assign a shift to employees for a date range.

    An employee can hold only one active assignment covering any given day, so
    an overlapping range is rejected rather than silently creating ambiguity
    about which shift applies.
    """
    get_shift(db, shift_id)
    created = []

    for employee_id in employee_ids:
        employee = db.get(Employee, employee_id)
        if employee is None or employee.is_deleted:
            raise NotFoundError(f"Employee {employee_id} not found.")

        existing = (
            db.execute(
                select(ShiftAssignment).where(
                    ShiftAssignment.employee_id == employee_id,
                    ShiftAssignment.is_active.is_(True),
                )
            )
            .scalars()
            .all()
        )
        for assignment in existing:
            if _overlaps(assignment, start_date, end_date):
                raise BusinessRuleError(
                    f"{employee.full_name} already has a shift assigned that "
                    f"overlaps {start_date}"
                    + (f" to {end_date}." if end_date else " onwards.")
                )

        record = ShiftAssignment(
            employee_id=employee_id,
            shift_id=shift_id,
            start_date=start_date,
            end_date=end_date,
            assigned_by_id=actor_id,
        )
        db.add(record)
        created.append(record)

    db.commit()
    for record in created:
        db.refresh(record)
    return created


def shift_for_employee(db: Session, employee_id: int, on: date) -> Optional[Shift]:
    """The shift covering a given date, if any."""
    assignment = db.execute(
        select(ShiftAssignment)
        .where(
            ShiftAssignment.employee_id == employee_id,
            ShiftAssignment.is_active.is_(True),
            ShiftAssignment.start_date <= on,
            or_(
                ShiftAssignment.end_date.is_(None),
                ShiftAssignment.end_date >= on,
            ),
        )
        .order_by(ShiftAssignment.start_date.desc())
    ).scalars().first()

    return db.get(Shift, assignment.shift_id) if assignment else None


def build_roster(db: Session, on: date, department_id: Optional[int] = None) -> List[dict]:
    stmt = select(Employee).where(
        Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None)
    )
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)

    roster = []
    for employee in db.execute(stmt.order_by(Employee.employee_code)).scalars().all():
        shift = shift_for_employee(db, employee.id, on)
        roster.append(
            {
                "employee_id": employee.id,
                "employee_code": employee.employee_code,
                "full_name": employee.full_name,
                "shift_code": shift.code if shift else None,
                "shift_name": shift.name if shift else None,
                "start_time": shift.start_time if shift else None,
                "end_time": shift.end_time if shift else None,
            }
        )
    return roster
