"""
Feature assembly for the attrition model.

Two rules govern everything here.

**Leakage.** A feature is only usable if its value would have been known at the
moment we want to predict. Exit date, exit reason and employment status are all
recorded *because* someone left, so including them would produce a model that
scores 99% in testing and is useless in production. They are excluded by name,
not by accident.

**Fairness.** Gender, marital status and date of birth are excluded by default.
They appear in standard HR datasets and are often predictive, but acting on a
prediction materially driven by marital status is a discrimination exposure.
The flag exists so the choice is explicit and reviewable, not so it is casually
flipped.
"""

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.department import Department, Designation
from app.models.employee import Employee
from app.models.enums import (
    AttendanceStatus,
    EmployeeStatus,
    LeaveStatus,
)
from app.models.leave import LeaveRequest, LeaveType

# Never usable as features: recorded at or after the exit decision.
LEAKY_COLUMNS = {
    "date_of_exit",
    "exit_reason",
    "status",
    "current_risk_score",
    "current_risk_level",
    "last_risk_evaluated_at",
    "is_deleted",
    "deleted_at",
}

# Excluded unless include_protected is explicitly set.
PROTECTED_COLUMNS = {"gender", "marital_status", "date_of_birth", "age"}

# Exits counted as attrition. A termination is the company's decision, not the
# employee's, so predicting it is a different problem.
VOLUNTARY_EXITS = {EmployeeStatus.RESIGNED}
ALL_EXITS = {
    EmployeeStatus.RESIGNED,
    EmployeeStatus.TERMINATED,
    EmployeeStatus.RETIRED,
}

NUMERIC_FEATURES = [
    "tenure_months",
    "age_years",
    "total_experience_years",
    "distance_from_home_km",
    "num_companies_worked",
    "training_hours_last_year",
    "job_satisfaction_score",
    "work_life_balance_score",
    "environment_satisfaction_score",
    "last_performance_rating",
    "months_since_last_promotion",
    "months_since_last_hike",
    "last_hike_percent",
    "salary_percentile_in_band",
    "absence_rate",
    "late_rate",
    "overtime_ratio",
    "leave_utilisation",
    "team_size",
    "notice_period_days",
]

CATEGORICAL_FEATURES = [
    "department_name",
    "designation_title",
    "employment_type",
    "work_mode",
    "education_level",
    "business_travel_frequency",
    "overtime_flag",
    "has_manager",
]


def _months_between(earlier: Optional[date], later: date) -> Optional[float]:
    if earlier is None:
        return None
    return round((later - earlier).days / 30.44, 1)


def _behaviour_window(
    db: Session,
    employees: List[Employee],
    as_of: date,
    window_days: int = 180,
) -> Dict[int, Dict[str, Optional[float]]]:
    """
    Attendance and leave signals over a trailing window, anchored **per
    employee**.

    This is the point-in-time correctness rule. For someone still employed the
    window ends today; for a leaver it ends on their exit date. Anchoring
    everyone at today would give leavers an empty or truncated window, and the
    model would learn to detect the gap in the data rather than the behaviour
    that preceded the resignation.

    Rates are returned rather than counts. A count of observed days is itself a
    label proxy -- a leaver simply has fewer of them.
    """
    if not employees:
        return {}

    anchors: Dict[int, Tuple[date, date]] = {}
    for emp in employees:
        end = min(emp.date_of_exit, as_of) if emp.date_of_exit else as_of
        anchors[emp.id] = (end - timedelta(days=window_days), end)

    earliest = min(start for start, _ in anchors.values())
    latest = max(end for _, end in anchors.values())

    rows = db.execute(
        select(
            Attendance.employee_id,
            Attendance.attendance_date,
            Attendance.status,
            Attendance.overtime_hours,
            Attendance.worked_hours,
        ).where(
            Attendance.employee_id.in_(list(anchors.keys())),
            Attendance.attendance_date >= earliest,
            Attendance.attendance_date <= latest,
        )
    ).all()

    buckets: Dict[int, Dict[str, float]] = {
        emp_id: {"present": 0.0, "absent": 0.0, "late": 0.0, "total": 0.0,
                 "overtime_hours": 0.0, "worked_hours": 0.0}
        for emp_id in anchors
    }

    for emp_id, day, status, overtime, worked in rows:
        start, end = anchors[emp_id]
        if day < start or day > end:
            continue  # outside this employee's own window
        bucket = buckets[emp_id]
        bucket["total"] += 1
        bucket["overtime_hours"] += float(overtime or 0)
        bucket["worked_hours"] += float(worked or 0)
        if status == AttendanceStatus.ABSENT:
            bucket["absent"] += 1
        elif status == AttendanceStatus.LATE:
            bucket["late"] += 1
            bucket["present"] += 1
        elif status in {
            AttendanceStatus.PRESENT,
            AttendanceStatus.WORK_FROM_HOME,
            AttendanceStatus.HALF_DAY,
        }:
            bucket["present"] += 1

    leave_rows = db.execute(
        select(
            LeaveRequest.employee_id,
            LeaveRequest.start_date,
            LeaveRequest.total_days,
        ).where(
            LeaveRequest.employee_id.in_(list(anchors.keys())),
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.start_date >= earliest,
            LeaveRequest.start_date <= latest,
        )
    ).all()

    leave_taken: Dict[int, float] = {emp_id: 0.0 for emp_id in anchors}
    for emp_id, start_date, total_days in leave_rows:
        start, end = anchors[emp_id]
        if start <= start_date <= end:
            leave_taken[emp_id] += float(total_days or 0)

    out: Dict[int, Dict[str, Optional[float]]] = {}
    for emp_id, bucket in buckets.items():
        total = bucket["total"]
        worked = bucket["worked_hours"]

        # No rows in the window means unknown, not perfect attendance. Zero
        # here would again make the absence of data a signal.
        if total == 0:
            out[emp_id] = {
                "absence_rate": None,
                "late_rate": None,
                "overtime_ratio": None,
                "leave_utilisation": round(leave_taken.get(emp_id, 0.0), 2),
            }
            continue

        out[emp_id] = {
            "absence_rate": round(bucket["absent"] / total, 4),
            "late_rate": round(bucket["late"] / total, 4),
            "overtime_ratio": (
                round(bucket["overtime_hours"] / worked, 4) if worked else None
            ),
            "leave_utilisation": round(leave_taken.get(emp_id, 0.0), 2),
        }
    return out


def _salary_percentiles(employees: List[Employee]) -> Dict[int, float]:
    """Where each employee sits within their own designation's salary band."""
    by_band: Dict[Optional[int], List[Tuple[int, float]]] = {}
    for emp in employees:
        if emp.current_salary is None:
            continue
        by_band.setdefault(emp.designation_id, []).append(
            (emp.id, float(emp.current_salary))
        )

    percentiles: Dict[int, float] = {}
    for _, members in by_band.items():
        salaries = np.array([s for _, s in members])
        for emp_id, salary in members:
            percentiles[emp_id] = round(
                float((salaries < salary).mean() * 100), 2
            )
    return percentiles


def build_feature_frame(
    db: Session,
    employees: Optional[List[Employee]] = None,
    as_of: Optional[date] = None,
    include_protected: bool = False,
) -> pd.DataFrame:
    """One row per employee, features only -- no label."""
    as_of = as_of or date.today()

    if employees is None:
        employees = (
            db.execute(select(Employee).where(Employee.is_deleted.is_(False)))
            .scalars()
            .all()
        )
    if not employees:
        return pd.DataFrame()

    behaviour = _behaviour_window(db, employees, as_of)
    percentiles = _salary_percentiles(employees)

    departments = {
        d.id: d.name for d in db.execute(select(Department)).scalars().all()
    }
    designations = {
        d.id: d.title for d in db.execute(select(Designation)).scalars().all()
    }
    team_sizes = dict(
        db.execute(
            select(Employee.manager_id, func.count(Employee.id))
            .where(Employee.is_deleted.is_(False))
            .group_by(Employee.manager_id)
        ).all()
    )

    records = []
    for emp in employees:
        signals = behaviour.get(
            emp.id,
            {"absence_rate": None, "late_rate": None, "overtime_ratio": None,
             "leave_utilisation": 0.0},
        )
        reference = min(emp.date_of_exit, as_of) if emp.date_of_exit else as_of

        row = {
            "employee_id": emp.id,
            "employee_code": emp.employee_code,
            "tenure_months": _months_between(emp.date_of_joining, reference) or 0.0,
            "age_years": (
                round((reference - emp.date_of_birth).days / 365.25, 1)
                if emp.date_of_birth
                else None
            ),
            "total_experience_years": emp.total_experience_years,
            "distance_from_home_km": emp.distance_from_home_km,
            "num_companies_worked": emp.num_companies_worked,
            "training_hours_last_year": emp.training_hours_last_year,
            "job_satisfaction_score": emp.job_satisfaction_score,
            "work_life_balance_score": emp.work_life_balance_score,
            "environment_satisfaction_score": emp.environment_satisfaction_score,
            "last_performance_rating": emp.last_performance_rating,
            "months_since_last_promotion": _months_between(
                emp.last_promotion_date or emp.date_of_joining, reference
            ),
            "months_since_last_hike": _months_between(
                emp.last_hike_date or emp.date_of_joining, reference
            ),
            "last_hike_percent": emp.last_hike_percent or 0.0,
            "salary_percentile_in_band": percentiles.get(emp.id),
            "notice_period_days": emp.notice_period_days,
            "team_size": float(team_sizes.get(emp.id, 0)),
            "department_name": departments.get(emp.department_id) or "Unassigned",
            "designation_title": designations.get(emp.designation_id) or "Unassigned",
            "employment_type": emp.employment_type.value if emp.employment_type else None,
            "work_mode": emp.work_mode.value if emp.work_mode else None,
            "education_level": emp.education_level or "Unknown",
            "business_travel_frequency": emp.business_travel_frequency or "Unknown",
            "overtime_flag": "yes" if emp.overtime_flag else "no",
            "has_manager": "yes" if emp.manager_id else "no",
            **signals,
        }

        if include_protected:
            row["gender"] = emp.gender.value if emp.gender else "undisclosed"
            row["marital_status"] = (
                emp.marital_status.value if emp.marital_status else "unknown"
            )

        records.append(row)

    return pd.DataFrame.from_records(records)


def build_training_frame(
    db: Session,
    horizon_days: int = 180,
    voluntary_only: bool = True,
    include_protected: bool = False,
) -> Tuple[pd.DataFrame, pd.Series, dict]:
    """
    Features and labels for training.

    The label is "left within `horizon_days` of the reference point", not "left
    at any time" -- a model that says someone will leave eventually tells HR
    nothing they can act on.
    """
    employees = (
        db.execute(select(Employee).where(Employee.is_deleted.is_(False)))
        .scalars()
        .all()
    )
    if not employees:
        return pd.DataFrame(), pd.Series(dtype=int), {}

    exit_statuses = VOLUNTARY_EXITS if voluntary_only else ALL_EXITS

    labels = []
    kept = []
    for emp in employees:
        if emp.date_of_exit:
            if emp.status not in exit_statuses:
                continue  # a termination is not voluntary attrition
            tenure_days = (emp.date_of_exit - emp.date_of_joining).days
            labels.append(1 if tenure_days >= 0 else 0)
        else:
            labels.append(0)
        kept.append(emp)

    frame = build_feature_frame(
        db, employees=kept, include_protected=include_protected
    )
    target = pd.Series(labels, name="attrition", index=frame.index)

    positives = int(target.sum())
    meta = {
        "rows": len(frame),
        "positives": positives,
        "negatives": len(target) - positives,
        "positive_rate": round(positives / len(target), 4) if len(target) else 0.0,
        "horizon_days": horizon_days,
        "voluntary_only": voluntary_only,
        "protected_attributes_included": include_protected,
        "excluded_for_leakage": sorted(LEAKY_COLUMNS),
        "excluded_as_protected": (
            [] if include_protected else sorted(PROTECTED_COLUMNS)
        ),
    }
    return frame, target, meta


def feature_columns(frame: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """Split into numeric and categorical, ignoring identifier columns."""
    ignore = {"employee_id", "employee_code", "attrition"}
    numeric = [
        c for c in frame.columns
        if c not in ignore and pd.api.types.is_numeric_dtype(frame[c])
    ]
    categorical = [
        c for c in frame.columns
        if c not in ignore and c not in numeric
    ]
    return numeric, categorical
