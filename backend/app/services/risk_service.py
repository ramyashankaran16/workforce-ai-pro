"""
Composite risk scoring.

The ML probability answers "will this person leave". It does not answer "why,
and what could we do about it". So the composite score blends the model output
with behavioural sub-scores that map to actions a manager can actually take:
pay, promotion, workload, engagement.

Every sub-score is normalised to 0-100 where higher means more risk, and the
weights are explicit and stored on each score row, so a number on a dashboard
can always be taken apart.
"""

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.ml import registry
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.enums import (
    AlertStatus,
    AttendanceStatus,
    LeaveStatus,
    Priority,
    RiskLevel,
    RiskTrend,
)
from app.models.leave import LeaveRequest
from app.models.prediction import AttritionPrediction
from app.models.risk import RiskAlert, RiskFactor, RiskScore
from app.services import prediction_service
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)

# Weights sum to 1.0. The model carries the most weight but never all of it --
# a purely model-driven score would give HR nothing to act on.
WEIGHTS: Dict[str, float] = {
    "ml_probability_score": 0.35,
    "compensation_score": 0.15,
    "engagement_score": 0.15,
    "workload_score": 0.10,
    "attendance_score": 0.10,
    "performance_score": 0.05,
    "tenure_score": 0.05,
    "leave_pattern_score": 0.05,
}

BANDS = [(75.0, RiskLevel.CRITICAL), (55.0, RiskLevel.HIGH),
         (35.0, RiskLevel.MEDIUM), (0.0, RiskLevel.LOW)]

TREND_TOLERANCE = 3.0  # points of movement before a trend is called


def band_for(score: float) -> RiskLevel:
    for floor, level in BANDS:
        if score >= floor:
            return level
    return RiskLevel.LOW


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


# ------------------------------------------------------------------ sub-scores
def _compensation(employee: Employee, percentile: Optional[float]) -> Tuple[float, str]:
    """Pay below the band and a long gap since the last revision both raise risk."""
    score = 0.0
    notes = []

    if percentile is not None:
        if percentile < 25:
            score += 55
            notes.append(f"pay in the bottom quartile of the band ({percentile:.0f}th)")
        elif percentile < 50:
            score += 30
            notes.append(f"pay below the band median ({percentile:.0f}th)")

    if employee.last_hike_date:
        months = (date.today() - employee.last_hike_date).days / 30.44
        if months > 24:
            score += 35
            notes.append(f"no salary revision in {months:.0f} months")
        elif months > 15:
            score += 18
            notes.append(f"last revision {months:.0f} months ago")

    if employee.last_promotion_date:
        months = (date.today() - employee.last_promotion_date).days / 30.44
        if months > 36:
            score += 25
            notes.append(f"no promotion in {months:.0f} months")

    return _clamp(score), "; ".join(notes)


def _engagement(employee: Employee) -> Tuple[float, str]:
    scores = [
        ("job satisfaction", employee.job_satisfaction_score),
        ("work-life balance", employee.work_life_balance_score),
        ("environment satisfaction", employee.environment_satisfaction_score),
    ]
    known = [(label, value) for label, value in scores if value is not None]
    if not known:
        return 50.0, "no engagement scores recorded"

    average = sum(value for _, value in known) / len(known)
    # 1-5 scale inverted: 5 means no risk, 1 means maximum
    score = _clamp((5 - average) / 4 * 100)
    weakest = min(known, key=lambda kv: kv[1])
    note = f"lowest signal is {weakest[0]} at {weakest[1]:.0f}/5" if weakest[1] <= 3 else ""
    return score, note


def _workload(employee: Employee, overtime_ratio: Optional[float]) -> Tuple[float, str]:
    score = 0.0
    notes = []
    if employee.overtime_flag:
        score += 35
        notes.append("flagged as regularly working overtime")
    if overtime_ratio is not None and overtime_ratio > 0.10:
        score += min(overtime_ratio * 250, 50)
        notes.append(f"overtime is {overtime_ratio:.0%} of hours worked")
    return _clamp(score), "; ".join(notes)


def _attendance(absence_rate: Optional[float], late_rate: Optional[float]) -> Tuple[float, str]:
    if absence_rate is None and late_rate is None:
        return 30.0, "no recent attendance data"

    score = 0.0
    notes = []
    if absence_rate is not None and absence_rate > 0.05:
        score += min(absence_rate * 400, 60)
        notes.append(f"absent on {absence_rate:.0%} of recorded days")
    if late_rate is not None and late_rate > 0.15:
        score += min(late_rate * 150, 40)
        notes.append(f"late on {late_rate:.0%} of recorded days")
    return _clamp(score), "; ".join(notes)


def _performance(employee: Employee) -> Tuple[float, str]:
    rating = employee.last_performance_rating
    if rating is None:
        return 40.0, "no performance rating on record"
    if rating <= 2:
        return 70.0, f"performance rating {rating}/5"
    if rating >= 4.5:
        # strong performers are the ones competitors approach
        return 45.0, f"high performer ({rating}/5) and a retention target"
    return _clamp((5 - rating) / 3 * 60), ""


def _tenure(employee: Employee) -> Tuple[float, str]:
    months = employee.tenure_months or 0
    if months < 12:
        return 70.0, f"only {months} months in role"
    if months < 24:
        return 45.0, f"{months} months in role"
    if months > 60:
        return 20.0, ""
    return 30.0, ""


def _leave_pattern(db: Session, employee_id: int) -> Tuple[float, str]:
    """
    Recent short-notice absences can precede a resignation.

    Deliberately weighted low: it is a weak signal and over-weighting it would
    penalise people for legitimately using their leave.
    """
    since = date.today() - timedelta(days=90)
    requests = (
        db.execute(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.start_date >= since,
            )
        )
        .scalars()
        .all()
    )
    short_notice = sum(
        1 for r in requests
        if (r.start_date - r.created_at.date()).days <= 2
    )
    if short_notice >= 3:
        return 60.0, f"{short_notice} short-notice leave requests in 90 days"
    if short_notice == 2:
        return 35.0, "two short-notice leave requests recently"
    return 15.0, ""


# ---------------------------------------------------------------------- scoring
def evaluate_employee(
    db: Session, employee: Employee, on: Optional[date] = None
) -> RiskScore:
    """Compute and persist a composite score with its contributing factors."""
    from app.ml import feature_engineering

    on = on or date.today()

    frame = feature_engineering.build_feature_frame(db, employees=[employee])
    row = frame.iloc[0] if not frame.empty else {}

    def get(key):
        value = row.get(key) if hasattr(row, "get") else None
        return None if value is None or value != value else float(value)

    # ML probability, if a model is deployed and has scored this person
    latest = db.execute(
        select(AttritionPrediction)
        .where(AttritionPrediction.employee_id == employee.id)
        .order_by(AttritionPrediction.predicted_at.desc())
    ).scalars().first()

    ml_score = None
    prediction_id = None
    if latest:
        ml_score = _clamp(latest.attrition_probability * 100)
        prediction_id = latest.id

    compensation, comp_note = _compensation(employee, get("salary_percentile_in_band"))
    engagement, eng_note = _engagement(employee)
    workload, work_note = _workload(employee, get("overtime_ratio"))
    attendance, att_note = _attendance(get("absence_rate"), get("late_rate"))
    performance, perf_note = _performance(employee)
    tenure, ten_note = _tenure(employee)
    leave, leave_note = _leave_pattern(db, employee.id)

    components = {
        "ml_probability_score": ml_score,
        "compensation_score": compensation,
        "engagement_score": engagement,
        "workload_score": workload,
        "attendance_score": attendance,
        "performance_score": performance,
        "tenure_score": tenure,
        "leave_pattern_score": leave,
    }

    # Redistribute the ML weight when no prediction exists, rather than
    # scoring a zero and quietly halving everyone's risk.
    available = {k: v for k, v in components.items() if v is not None}
    weight_total = sum(WEIGHTS[k] for k in available)
    overall = _clamp(
        sum(WEIGHTS[k] * v for k, v in available.items()) / weight_total
        if weight_total else 0.0
    )

    previous = db.execute(
        select(RiskScore)
        .where(RiskScore.employee_id == employee.id)
        .order_by(RiskScore.evaluation_date.desc(), RiskScore.id.desc())
    ).scalars().first()

    trend = RiskTrend.STABLE
    change = None
    if previous:
        change = round(overall - previous.overall_score, 2)
        if change > TREND_TOLERANCE:
            trend = RiskTrend.WORSENING
        elif change < -TREND_TOLERANCE:
            trend = RiskTrend.IMPROVING

    level = band_for(overall)
    record = RiskScore(
        employee_id=employee.id,
        prediction_id=prediction_id,
        evaluation_date=on,
        overall_score=overall,
        risk_level=level,
        trend=trend,
        previous_score=previous.overall_score if previous else None,
        score_change=change,
        ml_probability_score=ml_score,
        attendance_score=attendance,
        leave_pattern_score=leave,
        workload_score=workload,
        performance_score=performance,
        compensation_score=compensation,
        tenure_score=tenure,
        engagement_score=engagement,
        breakdown={
            "weights": {k: WEIGHTS[k] for k in available},
            "components": available,
            "weight_total_used": round(weight_total, 3),
            "ml_available": ml_score is not None,
        },
    )
    db.add(record)
    db.flush()

    notes = [
        ("Compensation", compensation, comp_note, "compensation"),
        ("Engagement", engagement, eng_note, "engagement"),
        ("Workload", workload, work_note, "workload"),
        ("Attendance", attendance, att_note, "attendance"),
        ("Performance", performance, perf_note, "performance"),
        ("Tenure", tenure, ten_note, "tenure"),
        ("Leave pattern", leave, leave_note, "leave"),
    ]
    for label, value, note, category in notes:
        if value >= 40 or note:
            db.add(
                RiskFactor(
                    risk_score_id=record.id,
                    factor_name=label,
                    factor_category=category,
                    contribution=round(WEIGHTS.get(f"{category}_score", 0.05) * value, 2),
                    current_value=str(round(value, 1)),
                    is_negative=True,
                    description=note or f"{label} sub-score is {value:.0f}/100",
                )
            )

    record.summary = _summarise(employee, overall, level, notes)

    employee.current_risk_score = overall
    employee.current_risk_level = level.value
    employee.last_risk_evaluated_at = utcnow()

    db.commit()
    db.refresh(record)
    return record


def _summarise(employee, overall, level, notes) -> str:
    drivers = sorted(
        [(label, value, note) for label, value, note, _ in notes if value >= 45],
        key=lambda t: t[1],
        reverse=True,
    )[:3]
    if not drivers:
        return f"{employee.full_name} scores {overall:.0f}/100 ({level.value}). No sub-score stands out."

    parts = [note or label.lower() for label, _, note in drivers]
    return (
        f"{employee.full_name} scores {overall:.0f}/100 ({level.value}). "
        f"Main drivers: {'; '.join(parts)}."
    )


def evaluate_all(db: Session, on: Optional[date] = None) -> dict:
    """Score every active employee."""
    employees = (
        db.execute(
            select(Employee).where(
                Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None)
            )
        )
        .scalars()
        .all()
    )
    if not employees:
        raise BusinessRuleError("There are no active employees to evaluate.")

    counts = {level: 0 for level in RiskLevel}
    for employee in employees:
        record = evaluate_employee(db, employee, on)
        counts[record.risk_level] += 1

    return {
        "evaluated": len(employees),
        "critical": counts[RiskLevel.CRITICAL],
        "high": counts[RiskLevel.HIGH],
        "medium": counts[RiskLevel.MEDIUM],
        "low": counts[RiskLevel.LOW],
    }


# ----------------------------------------------------------------------- alerts
def raise_alert(
    db: Session,
    employee: Employee,
    score: RiskScore,
    rule_id: Optional[int] = None,
    assigned_to_id: Optional[int] = None,
) -> RiskAlert:
    alert = RiskAlert(
        employee_id=employee.id,
        risk_score_id=score.id,
        alert_rule_id=rule_id,
        title=f"{employee.full_name} is at {score.risk_level.value} attrition risk",
        message=score.summary or "",
        risk_level=score.risk_level,
        priority=(
            Priority.CRITICAL if score.risk_level == RiskLevel.CRITICAL
            else Priority.HIGH if score.risk_level == RiskLevel.HIGH
            else Priority.MEDIUM
        ),
        status=AlertStatus.NEW,
        assigned_to_id=assigned_to_id,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def acknowledge(db: Session, alert_id: int, user_id: int) -> RiskAlert:
    alert = db.get(RiskAlert, alert_id)
    if alert is None:
        raise NotFoundError("Alert not found.")
    if alert.status in {AlertStatus.RESOLVED, AlertStatus.DISMISSED}:
        raise BusinessRuleError(f"Alert is already {alert.status.value}.")

    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_by_id = user_id
    alert.acknowledged_at = utcnow()
    db.commit()
    db.refresh(alert)
    return alert


def resolve(db: Session, alert_id: int, user_id: int, notes: str,
            dismiss: bool = False) -> RiskAlert:
    alert = db.get(RiskAlert, alert_id)
    if alert is None:
        raise NotFoundError("Alert not found.")
    if alert.status in {AlertStatus.RESOLVED, AlertStatus.DISMISSED}:
        raise BusinessRuleError(f"Alert is already {alert.status.value}.")

    alert.status = AlertStatus.DISMISSED if dismiss else AlertStatus.RESOLVED
    alert.resolved_at = utcnow()
    alert.resolution_notes = notes
    if alert.acknowledged_by_id is None:
        alert.acknowledged_by_id = user_id
        alert.acknowledged_at = utcnow()
    db.commit()
    db.refresh(alert)
    return alert


def department_heatmap(db: Session) -> List[dict]:
    """Risk distribution per department, for the dashboard."""
    from app.models.department import Department

    rows = db.execute(
        select(
            Department.id,
            Department.name,
            func.count(Employee.id),
            func.avg(Employee.current_risk_score),
        )
        .join(Employee, Employee.department_id == Department.id)
        .where(
            Employee.is_deleted.is_(False),
            Employee.date_of_exit.is_(None),
        )
        .group_by(Department.id, Department.name)
    ).all()

    out = []
    for dept_id, name, headcount, average in rows:
        levels = db.execute(
            select(Employee.current_risk_level, func.count(Employee.id))
            .where(
                Employee.department_id == dept_id,
                Employee.is_deleted.is_(False),
                Employee.date_of_exit.is_(None),
            )
            .group_by(Employee.current_risk_level)
        ).all()
        distribution = {str(level): count for level, count in levels if level}
        high = distribution.get("high", 0) + distribution.get("critical", 0)
        out.append(
            {
                "department_id": dept_id,
                "department_name": name,
                "headcount": int(headcount),
                "average_risk_score": round(float(average or 0), 2),
                "high_risk_count": high,
                "high_risk_percent": (
                    round(high / headcount * 100, 1) if headcount else 0.0
                ),
                "distribution": distribution,
            }
        )
    return sorted(out, key=lambda d: d["average_risk_score"], reverse=True)
