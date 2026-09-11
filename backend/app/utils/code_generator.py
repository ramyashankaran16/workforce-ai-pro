"""Sequential reference generation: employee codes, payslip numbers, task refs."""

import re
from datetime import date
from typing import Optional, Type

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def next_sequential_code(
    db: Session,
    model: Type,
    column,
    prefix: str,
    width: int = 4,
) -> str:
    """
    Build the next code in a `PREFIX0001` series.

    Reads the current maximum rather than counting rows, so deleted records
    never cause a collision. Not safe under high concurrency on its own -- the
    caller relies on the column's unique constraint to catch a race and retry.
    """
    pattern = f"{prefix}%"
    rows = db.execute(select(column).where(column.like(pattern))).scalars().all()

    highest = 0
    matcher = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    for value in rows:
        match = matcher.match(value or "")
        if match:
            highest = max(highest, int(match.group(1)))

    return f"{prefix}{highest + 1:0{width}d}"


def generate_employee_code(db: Session, prefix: str = "EMP") -> str:
    from app.models.employee import Employee

    return next_sequential_code(db, Employee, Employee.employee_code, prefix, width=4)


def generate_payslip_number(db: Session, year: int, month: int) -> str:
    from app.models.payroll import Payslip

    prefix = f"PS{year}{month:02d}"
    return next_sequential_code(db, Payslip, Payslip.slip_number, prefix, width=5)


def generate_task_reference(db: Session) -> str:
    from app.models.workflow import Task

    return next_sequential_code(db, Task, Task.reference, "TSK", width=5)


def generate_payroll_reference(year: int, month: int) -> str:
    return f"PR{year}{month:02d}"
