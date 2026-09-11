"""
Workforce Stability Engine.

A single index is only useful if it can be taken apart. Every metric feeding it
is stored with its raw value, its normalised score, its weight and a benchmark,
so "the index is 63" can always be followed by "because of which numbers".

The weights are a stated judgement, not a discovered truth. They are defined in
one place and returned with every snapshot so nobody has to guess.
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models.attendance import Attendance
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import (
    AttendanceStatus,
    RiskTrend,
    StabilityGrade,
    TargetScope,
)
from app.models.stability import StabilityMetric, StabilitySnapshot

logger = logging.getLogger(__name__)

# metric -> (weight, benchmark, unit, higher_is_better)
METRIC_SPEC: Dict[str, tuple] = {
    "retention_rate": (0.25, 88.0, "%", True),
    "average_tenure_months": (0.15, 36.0, "months", True),
    "engagement_score": (0.20, 3.8, "/5", True),
    "risk_exposure": (0.20, 15.0, "% at risk", False),
    "attendance_rate": (0.10, 95.0, "%", True),
    "overtime_load": (0.10, 8.0, "% of hours", False),
}

GRADES = [
    (85.0, StabilityGrade.EXCELLENT),
    (70.0, StabilityGrade.GOOD),
    (55.0, StabilityGrade.MODERATE),
    (40.0, StabilityGrade.POOR),
    (0.0, StabilityGrade.CRITICAL),
]

TREND_TOLERANCE = 2.0


def grade_for(index: float) -> StabilityGrade:
    for floor, grade in GRADES:
        if index >= floor:
            return grade
    return StabilityGrade.CRITICAL


def normalise(value: Optional[float], benchmark: float, higher_is_better: bool) -> float:
    """
    Scale a raw metric to 0-100 against its benchmark.

    Hitting the benchmark exactly scores 100 and is capped there: a department
    with 99% retention is not twice as stable as one with 90%.
    """
    if value is None:
        return 50.0  # unknown is neutral, not good and not bad

    if higher_is_better:
        score = (value / benchmark) * 100 if benchmark else 0.0
    else:
        # below the benchmark is good; at twice the benchmark the score is zero
        score = (2 - (value / benchmark)) * 100 if benchmark else 0.0

    return round(max(0.0, min(100.0, score)), 2)


def _collect_metrics(
    db: Session, department_id: Optional[int], window_days: int = 180
) -> Dict[str, Optional[float]]:
    since = date.today() - timedelta(days=window_days)

    base = [Employee.is_deleted.is_(False)]
    if department_id:
        base.append(Employee.department_id == department_id)

    active = db.execute(
        select(func.count(Employee.id)).where(
            *base, Employee.date_of_exit.is_(None)
        )
    ).scalar() or 0

    exits = db.execute(
        select(func.count(Employee.id)).where(*base, Employee.date_of_exit >= since)
    ).scalar() or 0

    joiners = db.execute(
        select(func.count(Employee.id)).where(*base, Employee.date_of_joining >= since)
    ).scalar() or 0

    base_population = active + exits
    retention = (
        round((1 - exits / base_population) * 100, 2) if base_population else None
    )

    employees = (
        db.execute(select(Employee).where(*base, Employee.date_of_exit.is_(None)))
        .scalars()
        .all()
    )

    tenures = [e.tenure_months for e in employees if e.tenure_months is not None]
    average_tenure = round(sum(tenures) / len(tenures), 1) if tenures else None

    engagement_values = []
    for employee in employees:
        scores = [
            employee.job_satisfaction_score,
            employee.work_life_balance_score,
            employee.environment_satisfaction_score,
        ]
        known = [s for s in scores if s is not None]
        if known:
            engagement_values.append(sum(known) / len(known))
    engagement = (
        round(sum(engagement_values) / len(engagement_values), 2)
        if engagement_values
        else None
    )

    at_risk = sum(
        1 for e in employees if (e.current_risk_level or "") in {"high", "critical"}
    )
    risk_exposure = round(at_risk / len(employees) * 100, 2) if employees else None

    employee_ids = [e.id for e in employees]
    attendance_rate = None
    overtime_load = None
    if employee_ids:
        rows = db.execute(
            select(
                func.count(Attendance.id),
                func.sum(func.coalesce(Attendance.worked_hours, 0)),
                func.sum(func.coalesce(Attendance.overtime_hours, 0)),
            ).where(
                Attendance.employee_id.in_(employee_ids),
                Attendance.attendance_date >= since,
                Attendance.status.notin_(
                    [AttendanceStatus.WEEKEND, AttendanceStatus.HOLIDAY]
                ),
            )
        ).one()
        total_records, worked, overtime = rows

        if total_records:
            present = db.execute(
                select(func.count(Attendance.id)).where(
                    Attendance.employee_id.in_(employee_ids),
                    Attendance.attendance_date >= since,
                    Attendance.status.in_(
                        [
                            AttendanceStatus.PRESENT,
                            AttendanceStatus.LATE,
                            AttendanceStatus.WORK_FROM_HOME,
                        ]
                    ),
                )
            ).scalar() or 0
            attendance_rate = round(present / total_records * 100, 2)

        if worked:
            overtime_load = round(float(overtime or 0) / float(worked) * 100, 2)

    return {
        "retention_rate": retention,
        "average_tenure_months": average_tenure,
        "engagement_score": engagement,
        "risk_exposure": risk_exposure,
        "attendance_rate": attendance_rate,
        "overtime_load": overtime_load,
        # context, not scored
        "_headcount": len(employees),
        "_joiners": joiners,
        "_exits": exits,
        "_at_risk": at_risk,
        "_attrition_rate": (
            round(exits / base_population * 100, 2) if base_population else None
        ),
    }


def compute_snapshot(
    db: Session,
    department_id: Optional[int] = None,
    on: Optional[date] = None,
) -> StabilitySnapshot:
    on = on or date.today()
    scope = TargetScope.DEPARTMENT if department_id else TargetScope.ORGANISATION

    if department_id:
        department = db.get(Department, department_id)
        if department is None or department.is_deleted:
            raise NotFoundError("Department not found.")

    metrics = _collect_metrics(db, department_id)
    if metrics["_headcount"] == 0:
        raise BusinessRuleError("There are no active employees in this scope.")

    scored: Dict[str, Dict[str, Any]] = {}
    weighted_total = 0.0
    for name, (weight, benchmark, unit, higher_is_better) in METRIC_SPEC.items():
        raw = metrics.get(name)
        normalised = normalise(raw, benchmark, higher_is_better)
        scored[name] = {
            "value": raw,
            "normalised": normalised,
            "weight": weight,
            "benchmark": benchmark,
            "unit": unit,
            "higher_is_better": higher_is_better,
        }
        weighted_total += weight * normalised

    index = round(weighted_total, 2)
    grade = grade_for(index)

    previous = db.execute(
        select(StabilitySnapshot)
        .where(
            StabilitySnapshot.scope == scope,
            StabilitySnapshot.department_id == department_id,
            StabilitySnapshot.snapshot_date < on,
        )
        .order_by(StabilitySnapshot.snapshot_date.desc(), StabilitySnapshot.id.desc())
    ).scalars().first()

    trend = RiskTrend.STABLE
    if previous:
        change = index - previous.stability_index
        if change > TREND_TOLERANCE:
            trend = RiskTrend.IMPROVING
        elif change < -TREND_TOLERANCE:
            trend = RiskTrend.WORSENING

    # replace any snapshot already taken for this date and scope
    existing = db.execute(
        select(StabilitySnapshot).where(
            StabilitySnapshot.snapshot_date == on,
            StabilitySnapshot.scope == scope,
            StabilitySnapshot.department_id == department_id,
        )
    ).scalar_one_or_none()
    if existing:
        db.delete(existing)
        db.flush()

    snapshot = StabilitySnapshot(
        snapshot_date=on,
        scope=scope,
        department_id=department_id,
        stability_index=index,
        grade=grade,
        trend=trend,
        previous_index=previous.stability_index if previous else None,
        total_headcount=metrics["_headcount"],
        joiners_count=metrics["_joiners"],
        exits_count=metrics["_exits"],
        attrition_rate=metrics["_attrition_rate"],
        average_tenure_months=metrics["average_tenure_months"],
        high_risk_count=metrics["_at_risk"],
        average_risk_score=None,
        average_satisfaction=metrics["engagement_score"],
        absence_rate=(
            round(100 - metrics["attendance_rate"], 2)
            if metrics["attendance_rate"] is not None
            else None
        ),
        overtime_ratio=metrics["overtime_load"],
        breakdown={"metrics": scored, "weights": {k: v[0] for k, v in METRIC_SPEC.items()}},
        commentary=_commentary(index, grade, scored),
    )
    db.add(snapshot)
    db.flush()

    for name, detail in scored.items():
        db.add(
            StabilityMetric(
                snapshot_id=snapshot.id,
                metric_name=name,
                metric_category="workforce",
                value=detail["value"] if detail["value"] is not None else 0.0,
                normalised_score=detail["normalised"],
                weight=detail["weight"],
                benchmark=detail["benchmark"],
                unit=detail["unit"],
            )
        )

    db.commit()
    db.refresh(snapshot)
    return snapshot


def _commentary(index: float, grade: StabilityGrade, scored: Dict[str, dict]) -> str:
    weakest = sorted(scored.items(), key=lambda kv: kv[1]["normalised"])[:2]
    strongest = max(scored.items(), key=lambda kv: kv[1]["normalised"])

    weak_text = ", ".join(
        f"{name.replace('_', ' ')} ({detail['value']}{detail['unit']})"
        for name, detail in weakest
        if detail["value"] is not None
    )
    return (
        f"Stability index {index}/100 ({grade.value}). "
        f"Weakest: {weak_text or 'no metric stands out'}. "
        f"Strongest: {strongest[0].replace('_', ' ')}."
    )


def history(
    db: Session, department_id: Optional[int] = None, limit: int = 12
) -> List[StabilitySnapshot]:
    scope = TargetScope.DEPARTMENT if department_id else TargetScope.ORGANISATION
    return (
        db.execute(
            select(StabilitySnapshot)
            .where(
                StabilitySnapshot.scope == scope,
                StabilitySnapshot.department_id == department_id,
            )
            .order_by(StabilitySnapshot.snapshot_date.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def latest(db: Session, department_id: Optional[int] = None) -> StabilitySnapshot:
    rows = history(db, department_id, limit=1)
    if not rows:
        raise NotFoundError(
            "No stability snapshot yet. Run POST /stability/snapshot first."
        )
    return rows[0]


def compare_departments(db: Session, on: Optional[date] = None) -> List[dict]:
    """Compute a snapshot per department and rank them."""
    departments = (
        db.execute(select(Department).where(Department.is_deleted.is_(False)))
        .scalars()
        .all()
    )

    out = []
    for department in departments:
        try:
            snapshot = compute_snapshot(db, department.id, on)
        except BusinessRuleError:
            continue  # empty department
        out.append(
            {
                "department_id": department.id,
                "department_name": department.name,
                "stability_index": snapshot.stability_index,
                "grade": snapshot.grade.value,
                "trend": snapshot.trend.value,
                "headcount": snapshot.total_headcount,
                "attrition_rate": snapshot.attrition_rate,
                "high_risk_count": snapshot.high_risk_count,
            }
        )
    return sorted(out, key=lambda d: d["stability_index"], reverse=True)
