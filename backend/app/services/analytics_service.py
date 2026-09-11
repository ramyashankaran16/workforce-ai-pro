"""Attrition analytics aggregations for the dashboard."""

import calendar
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeStatus
from app.models.prediction import AttritionPrediction

TENURE_BUCKETS = [
    (0, 12, "0-1 year"),
    (12, 24, "1-2 years"),
    (24, 60, "2-5 years"),
    (60, 120, "5-10 years"),
    (120, 10_000, "10+ years"),
]


def _month_range(months: int) -> List[Tuple[date, date]]:
    out = []
    cursor = date.today().replace(day=1)
    for _ in range(months):
        end = date(cursor.year, cursor.month,
                   calendar.monthrange(cursor.year, cursor.month)[1])
        out.append((cursor, end))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return list(reversed(out))


def overview(db: Session, months: int = 12) -> dict:
    """Headline attrition figures plus the monthly trend."""
    active = db.execute(
        select(func.count(Employee.id)).where(
            Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None)
        )
    ).scalar() or 0

    window_start = _month_range(months)[0][0]
    exits = db.execute(
        select(func.count(Employee.id)).where(
            Employee.is_deleted.is_(False),
            Employee.date_of_exit >= window_start,
        )
    ).scalar() or 0

    voluntary = db.execute(
        select(func.count(Employee.id)).where(
            Employee.is_deleted.is_(False),
            Employee.date_of_exit >= window_start,
            Employee.status == EmployeeStatus.RESIGNED,
        )
    ).scalar() or 0

    average_headcount = active + (exits / 2) if active else 0
    rate = round(exits / average_headcount * 100, 2) if average_headcount else 0.0

    trend = []
    for start, end in _month_range(months):
        headcount = db.execute(
            select(func.count(Employee.id)).where(
                Employee.is_deleted.is_(False),
                Employee.date_of_joining <= end,
                or_(Employee.date_of_exit.is_(None), Employee.date_of_exit > end),
            )
        ).scalar() or 0
        month_exits = db.execute(
            select(func.count(Employee.id)).where(
                Employee.is_deleted.is_(False),
                Employee.date_of_exit >= start,
                Employee.date_of_exit <= end,
            )
        ).scalar() or 0
        joins = db.execute(
            select(func.count(Employee.id)).where(
                Employee.is_deleted.is_(False),
                Employee.date_of_joining >= start,
                Employee.date_of_joining <= end,
            )
        ).scalar() or 0

        trend.append(
            {
                "period": start.strftime("%b %Y"),
                "headcount": headcount,
                "joiners": joins,
                "exits": month_exits,
                "attrition_rate": (
                    round(month_exits / headcount * 100, 2) if headcount else 0.0
                ),
            }
        )

    at_risk = db.execute(
        select(func.count(Employee.id)).where(
            Employee.is_deleted.is_(False),
            Employee.date_of_exit.is_(None),
            Employee.current_risk_level.in_(["high", "critical"]),
        )
    ).scalar() or 0

    return {
        "active_headcount": active,
        "exits_in_window": exits,
        "voluntary_exits": voluntary,
        "involuntary_exits": exits - voluntary,
        "attrition_rate_percent": rate,
        "voluntary_rate_percent": (
            round(voluntary / average_headcount * 100, 2) if average_headcount else 0.0
        ),
        "employees_at_high_risk": at_risk,
        "window_months": months,
        "trend": trend,
    }


def by_department(db: Session, months: int = 12) -> List[dict]:
    window_start = _month_range(months)[0][0]
    rows = db.execute(
        select(Department.id, Department.name).order_by(Department.name)
    ).all()

    out = []
    for dept_id, name in rows:
        headcount = db.execute(
            select(func.count(Employee.id)).where(
                Employee.department_id == dept_id,
                Employee.is_deleted.is_(False),
                Employee.date_of_exit.is_(None),
            )
        ).scalar() or 0
        exits = db.execute(
            select(func.count(Employee.id)).where(
                Employee.department_id == dept_id,
                Employee.is_deleted.is_(False),
                Employee.date_of_exit >= window_start,
            )
        ).scalar() or 0
        at_risk = db.execute(
            select(func.count(Employee.id)).where(
                Employee.department_id == dept_id,
                Employee.is_deleted.is_(False),
                Employee.date_of_exit.is_(None),
                Employee.current_risk_level.in_(["high", "critical"]),
            )
        ).scalar() or 0

        base = headcount + exits
        out.append(
            {
                "department_id": dept_id,
                "department_name": name,
                "headcount": headcount,
                "exits": exits,
                "attrition_rate_percent": round(exits / base * 100, 2) if base else 0.0,
                "at_risk_count": at_risk,
            }
        )

    return sorted(out, key=lambda d: d["attrition_rate_percent"], reverse=True)


def by_tenure(db: Session) -> List[dict]:
    """
    Attrition by tenure band.

    The first year almost always dominates. Showing it this way is what turns
    "we have an attrition problem" into "we have an onboarding problem".
    """
    employees = (
        db.execute(select(Employee).where(Employee.is_deleted.is_(False)))
        .scalars()
        .all()
    )

    buckets = {label: {"total": 0, "exits": 0} for _, _, label in TENURE_BUCKETS}
    for employee in employees:
        months = employee.tenure_months or 0
        for low, high, label in TENURE_BUCKETS:
            if low <= months < high:
                buckets[label]["total"] += 1
                if employee.date_of_exit:
                    buckets[label]["exits"] += 1
                break

    return [
        {
            "tenure_band": label,
            "employees": data["total"],
            "exits": data["exits"],
            "attrition_rate_percent": (
                round(data["exits"] / data["total"] * 100, 2) if data["total"] else 0.0
            ),
        }
        for _, _, label in TENURE_BUCKETS
        for data in [buckets[label]]
    ]


def exit_reasons(db: Session, limit: int = 10) -> List[dict]:
    rows = db.execute(
        select(Employee.exit_reason, func.count(Employee.id))
        .where(
            Employee.is_deleted.is_(False),
            Employee.exit_reason.isnot(None),
        )
        .group_by(Employee.exit_reason)
        .order_by(func.count(Employee.id).desc())
        .limit(limit)
    ).all()
    total = sum(count for _, count in rows) or 1
    return [
        {
            "reason": reason,
            "count": int(count),
            "percent": round(count / total * 100, 1),
        }
        for reason, count in rows
    ]


def model_drivers(db: Session) -> dict:
    """Aggregate feature importance from the deployed model."""
    from app.ml import registry

    version = registry.deployed_model(db)
    if version is None:
        return {"model": None, "drivers": [], "note": "No model is deployed."}

    importance = version.feature_importance or {}
    drivers = [
        {"feature": name, "importance": value}
        for name, value in list(importance.items())[:15]
    ]
    return {
        "model": {
            "id": version.id,
            "name": version.name,
            "version": version.version,
            "algorithm": version.algorithm.value,
        },
        "drivers": drivers,
        "note": (
            "These describe the model globally. They do not explain any "
            "individual prediction -- use the per-employee explanation for that."
        ),
    }


def risk_distribution(db: Session) -> dict:
    rows = db.execute(
        select(Employee.current_risk_level, func.count(Employee.id))
        .where(
            Employee.is_deleted.is_(False),
            Employee.date_of_exit.is_(None),
            Employee.current_risk_level.isnot(None),
        )
        .group_by(Employee.current_risk_level)
    ).all()

    distribution = {str(level): int(count) for level, count in rows}
    unscored = db.execute(
        select(func.count(Employee.id)).where(
            Employee.is_deleted.is_(False),
            Employee.date_of_exit.is_(None),
            Employee.current_risk_level.is_(None),
        )
    ).scalar() or 0

    return {
        "distribution": distribution,
        "unscored": unscored,
        "total_scored": sum(distribution.values()),
    }


def cohort_retention(db: Session, cohort_months: int = 12) -> List[dict]:
    """Retention curve by joining cohort."""
    out = []
    for start, end in _month_range(cohort_months):
        cohort = (
            db.execute(
                select(Employee).where(
                    Employee.is_deleted.is_(False),
                    Employee.date_of_joining >= start,
                    Employee.date_of_joining <= end,
                )
            )
            .scalars()
            .all()
        )
        if not cohort:
            continue
        still_here = sum(1 for e in cohort if e.date_of_exit is None)
        out.append(
            {
                "cohort": start.strftime("%b %Y"),
                "joined": len(cohort),
                "retained": still_here,
                "retention_percent": round(still_here / len(cohort) * 100, 1),
            }
        )
    return out


# ---------------------------------------------------------------- dashboards
def dashboard_for(db: Session, user, employee) -> dict:
    """
    Role-scoped dashboard.

    One endpoint rather than four, because the tiles overlap heavily and the
    difference is the scope of the data, not its shape. What changes is which
    employees are counted and which sections are present at all.
    """
    from app.models.attendance import Attendance
    from app.models.enums import AttendanceStatus, LeaveStatus
    from app.models.leave import LeaveRequest
    from app.models.notification import Notification
    from app.models.risk import RiskAlert
    from app.models.enums import AlertStatus

    role = (user.role_name or "").lower()
    today = date.today()

    payload: Dict[str, Any] = {"role": role, "generated_for": user.full_name}

    # --- personal section, present for anyone with an employee profile
    if employee is not None:
        todays_record = db.execute(
            select(Attendance).where(
                Attendance.employee_id == employee.id,
                Attendance.attendance_date == today,
            )
        ).scalar_one_or_none()

        pending_leave = db.execute(
            select(func.count(LeaveRequest.id)).where(
                LeaveRequest.employee_id == employee.id,
                LeaveRequest.status == LeaveStatus.PENDING,
            )
        ).scalar() or 0

        payload["me"] = {
            "employee_code": employee.employee_code,
            "full_name": employee.full_name,
            "department": employee.department.name if employee.department else None,
            "designation": (
                employee.designation.title if employee.designation else None
            ),
            "checked_in_today": bool(todays_record and todays_record.check_in),
            "checked_out_today": bool(todays_record and todays_record.check_out),
            "todays_status": todays_record.status.value if todays_record else None,
            "pending_leave_requests": int(pending_leave),
            "tenure_months": employee.tenure_months,
        }

    payload["unread_notifications"] = int(
        db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user.id, Notification.is_read.is_(False)
            )
        ).scalar()
        or 0
    )

    if role == "employee":
        return payload

    # --- team or organisation scope
    scope_ids = None
    if role == "manager" and employee is not None:
        scope_ids = (
            db.execute(
                select(Employee.id).where(
                    Employee.manager_id == employee.id,
                    Employee.is_deleted.is_(False),
                )
            )
            .scalars()
            .all()
        )

    def scoped(stmt):
        return stmt.where(Employee.id.in_(scope_ids)) if scope_ids is not None else stmt

    headcount = db.execute(
        scoped(
            select(func.count(Employee.id)).where(
                Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None)
            )
        )
    ).scalar() or 0

    present_today = db.execute(
        select(func.count(Attendance.id))
        .join(Employee, Employee.id == Attendance.employee_id)
        .where(
            Attendance.attendance_date == today,
            Attendance.status.in_(
                [
                    AttendanceStatus.PRESENT,
                    AttendanceStatus.LATE,
                    AttendanceStatus.WORK_FROM_HOME,
                ]
            ),
            *([Employee.id.in_(scope_ids)] if scope_ids is not None else []),
        )
    ).scalar() or 0

    on_leave_today = db.execute(
        select(func.count(LeaveRequest.id))
        .join(Employee, Employee.id == LeaveRequest.employee_id)
        .where(
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.start_date <= today,
            LeaveRequest.end_date >= today,
            *([Employee.id.in_(scope_ids)] if scope_ids is not None else []),
        )
    ).scalar() or 0

    pending_approvals = db.execute(
        select(func.count(LeaveRequest.id))
        .join(Employee, Employee.id == LeaveRequest.employee_id)
        .where(
            LeaveRequest.status == LeaveStatus.PENDING,
            *([Employee.id.in_(scope_ids)] if scope_ids is not None else []),
        )
    ).scalar() or 0

    at_risk = db.execute(
        scoped(
            select(func.count(Employee.id)).where(
                Employee.is_deleted.is_(False),
                Employee.date_of_exit.is_(None),
                Employee.current_risk_level.in_(["high", "critical"]),
            )
        )
    ).scalar() or 0

    payload["team" if scope_ids is not None else "organisation"] = {
        "headcount": int(headcount),
        "present_today": int(present_today),
        "on_leave_today": int(on_leave_today),
        "absent_today": max(int(headcount) - int(present_today) - int(on_leave_today), 0),
        "attendance_percent": (
            round(present_today / headcount * 100, 1) if headcount else 0.0
        ),
        "pending_leave_approvals": int(pending_approvals),
        "employees_at_risk": int(at_risk),
    }

    if role in {"admin", "hr"}:
        open_alerts = db.execute(
            select(func.count(RiskAlert.id)).where(
                RiskAlert.status.in_(
                    [AlertStatus.NEW, AlertStatus.ACKNOWLEDGED, AlertStatus.IN_PROGRESS]
                )
            )
        ).scalar() or 0

        joiners = db.execute(
            select(func.count(Employee.id)).where(
                Employee.is_deleted.is_(False),
                Employee.date_of_joining >= today - timedelta(days=30),
            )
        ).scalar() or 0
        exits = db.execute(
            select(func.count(Employee.id)).where(
                Employee.is_deleted.is_(False),
                Employee.date_of_exit >= today - timedelta(days=30),
            )
        ).scalar() or 0

        payload["organisation"].update(
            {
                "open_risk_alerts": int(open_alerts),
                "joiners_last_30_days": int(joiners),
                "exits_last_30_days": int(exits),
            }
        )
        payload["risk_distribution"] = risk_distribution(db)

    return payload


def headcount_breakdown(db: Session) -> dict:
    from app.models.enums import EmploymentType, WorkMode

    def group(column):
        rows = db.execute(
            select(column, func.count(Employee.id))
            .where(Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None))
            .group_by(column)
        ).all()
        return {
            str(key.value if hasattr(key, "value") else key or "Unassigned"): int(count)
            for key, count in rows
        }

    departments = db.execute(
        select(Department.name, func.count(Employee.id))
        .join(Employee, Employee.department_id == Department.id)
        .where(Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None))
        .group_by(Department.name)
    ).all()

    return {
        "by_department": {name: int(count) for name, count in departments},
        "by_employment_type": group(Employee.employment_type),
        "by_work_mode": group(Employee.work_mode),
        "total": int(
            db.execute(
                select(func.count(Employee.id)).where(
                    Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None)
                )
            ).scalar()
            or 0
        ),
    }


def live_snapshot(db: Session) -> dict:
    """Current-moment view for the monitoring dashboard."""
    from app.models.attendance import Attendance
    from app.models.enums import AttendanceStatus, LeaveStatus
    from app.models.leave import LeaveRequest

    today = date.today()
    headcount = db.execute(
        select(func.count(Employee.id)).where(
            Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None)
        )
    ).scalar() or 0

    checked_in = db.execute(
        select(func.count(Attendance.id)).where(
            Attendance.attendance_date == today,
            Attendance.check_in.isnot(None),
            Attendance.check_out.is_(None),
        )
    ).scalar() or 0

    completed = db.execute(
        select(func.count(Attendance.id)).where(
            Attendance.attendance_date == today,
            Attendance.check_out.isnot(None),
        )
    ).scalar() or 0

    on_leave = db.execute(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.start_date <= today,
            LeaveRequest.end_date >= today,
        )
    ).scalar() or 0

    return {
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "headcount": int(headcount),
        "currently_working": int(checked_in),
        "completed_today": int(completed),
        "on_leave_today": int(on_leave),
        "not_yet_checked_in": max(
            int(headcount) - int(checked_in) - int(completed) - int(on_leave), 0
        ),
    }
