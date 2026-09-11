"""Workforce forecasting: headcount, attrition rate, hiring need, and scenarios."""

import calendar
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.ml import forecaster
from app.models.employee import Employee
from app.models.enums import ForecastGranularity, ForecastType
from app.models.forecast import ForecastDataPoint, ForecastScenario, WorkforceForecast

logger = logging.getLogger(__name__)


def _month_starts(end: date, count: int) -> List[date]:
    months = []
    cursor = date(end.year, end.month, 1)
    for _ in range(count):
        months.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return list(reversed(months))


def _month_end(start: date) -> date:
    return date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])


def historical_series(
    db: Session,
    forecast_type: ForecastType,
    periods: int = 12,
    department_id: Optional[int] = None,
) -> List[Tuple[date, float]]:
    """Monthly history for the chosen metric."""
    series: List[Tuple[date, float]] = []

    for month_start in _month_starts(date.today(), periods):
        month_end = _month_end(month_start)

        headcount_stmt = select(func.count(Employee.id)).where(
            Employee.is_deleted.is_(False),
            Employee.date_of_joining <= month_end,
            or_(Employee.date_of_exit.is_(None), Employee.date_of_exit > month_end),
        )
        exits_stmt = select(func.count(Employee.id)).where(
            Employee.is_deleted.is_(False),
            Employee.date_of_exit >= month_start,
            Employee.date_of_exit <= month_end,
        )
        joins_stmt = select(func.count(Employee.id)).where(
            Employee.is_deleted.is_(False),
            Employee.date_of_joining >= month_start,
            Employee.date_of_joining <= month_end,
        )

        if department_id:
            headcount_stmt = headcount_stmt.where(Employee.department_id == department_id)
            exits_stmt = exits_stmt.where(Employee.department_id == department_id)
            joins_stmt = joins_stmt.where(Employee.department_id == department_id)

        headcount = db.execute(headcount_stmt).scalar() or 0
        exits = db.execute(exits_stmt).scalar() or 0
        joins = db.execute(joins_stmt).scalar() or 0

        if forecast_type == ForecastType.HEADCOUNT:
            value = float(headcount)
        elif forecast_type == ForecastType.ATTRITION_RATE:
            # monthly separations as a percentage of the month-end headcount
            value = round((exits / headcount * 100), 3) if headcount else 0.0
        elif forecast_type == ForecastType.HIRING_NEED:
            value = float(max(exits - joins, 0))
        else:  # COST
            salary_stmt = select(func.sum(Employee.current_salary)).where(
                Employee.is_deleted.is_(False),
                Employee.date_of_joining <= month_end,
                or_(Employee.date_of_exit.is_(None), Employee.date_of_exit > month_end),
            )
            if department_id:
                salary_stmt = salary_stmt.where(Employee.department_id == department_id)
            value = float(db.execute(salary_stmt).scalar() or 0)

        series.append((month_start, value))

    return series


def create_forecast(
    db: Session,
    name: str,
    forecast_type: ForecastType,
    horizon_periods: int = 6,
    lookback_periods: int = 12,
    department_id: Optional[int] = None,
    confidence: float = 0.90,
    description: Optional[str] = None,
    actor_id: Optional[int] = None,
) -> WorkforceForecast:
    history = historical_series(db, forecast_type, lookback_periods, department_id)
    if not history:
        raise BusinessRuleError("There is no history to forecast from.")

    values = [value for _, value in history]
    ceiling = 100.0 if forecast_type == ForecastType.ATTRITION_RATE else None
    result = forecaster.project(values, horizon_periods, confidence, floor=0.0,
                                ceiling=ceiling)

    forecast = WorkforceForecast(
        name=name,
        description=description,
        forecast_type=forecast_type,
        granularity=ForecastGranularity.MONTHLY,
        department_id=department_id,
        period_start=history[0][0],
        period_end=_month_end(history[-1][0]),
        horizon_periods=horizon_periods,
        method=result["method"],
        baseline_value=round(values[-1], 3),
        projected_value=(
            result["points"][-1]["predicted"] if result["points"] else None
        ),
        confidence_level=confidence,
        assumptions={
            "lookback_periods": lookback_periods,
            "method": result["method"],
            "slope_per_month": result.get("slope"),
            "note": result.get("note"),
            "caveat": (
                "Linear extrapolation assumes conditions stay as they were. It "
                "cannot anticipate a reorganisation, a market shift or a policy "
                "change."
            ),
        },
        generated_by_id=actor_id,
    )
    db.add(forecast)
    db.flush()

    for month_start, value in history:
        db.add(
            ForecastDataPoint(
                forecast_id=forecast.id,
                period_label=month_start.strftime("%b %Y"),
                period_date=month_start,
                actual_value=value,
                predicted_value=value,
                is_projection=False,
            )
        )

    cursor = history[-1][0]
    for point in result["points"]:
        cursor = (_month_end(cursor) + timedelta(days=1))
        db.add(
            ForecastDataPoint(
                forecast_id=forecast.id,
                period_label=cursor.strftime("%b %Y"),
                period_date=cursor,
                actual_value=None,
                predicted_value=point["predicted"],
                lower_bound=point["lower_bound"],
                upper_bound=point["upper_bound"],
                is_projection=True,
            )
        )

    db.commit()
    db.refresh(forecast)
    return forecast


def get_forecast(db: Session, forecast_id: int) -> WorkforceForecast:
    forecast = db.get(WorkforceForecast, forecast_id)
    if forecast is None:
        raise NotFoundError("Forecast not found.")
    return forecast


def create_scenario(
    db: Session, forecast_id: int, data: dict, actor_id: Optional[int] = None
) -> ForecastScenario:
    """
    A what-if variant.

    Be clear about what this is: the adjustments are applied arithmetically to
    the projection. The model is not re-fitted, and nothing here establishes
    that a salary increase *causes* lower attrition -- it encodes an assumption
    the user supplies.
    """
    forecast = get_forecast(db, forecast_id)

    baseline = forecast.projected_value or forecast.baseline_value or 0.0
    attrition_change = data.get("attrition_rate_change", 0.0)
    hiring_change = data.get("hiring_rate_change", 0.0)
    salary_increase = data.get("salary_increase_percent", 0.0)

    # An assumed elasticity: each 1% of salary increase is taken to reduce
    # attrition by 0.4 percentage points. Stated, not discovered.
    salary_effect = -salary_increase * 0.4

    projected_attrition = None
    projected_headcount = None

    if forecast.forecast_type == ForecastType.ATTRITION_RATE:
        projected_attrition = max(
            round(baseline + attrition_change + salary_effect, 3), 0.0
        )
    elif forecast.forecast_type == ForecastType.HEADCOUNT:
        projected_headcount = max(round(baseline * (1 + hiring_change / 100), 2), 0.0)

    scenario = ForecastScenario(
        forecast_id=forecast.id,
        name=data["name"],
        description=data.get("description"),
        hiring_rate_change=hiring_change,
        attrition_rate_change=attrition_change,
        salary_increase_percent=salary_increase,
        parameters=data.get("parameters"),
        projected_attrition_rate=projected_attrition,
        projected_headcount=projected_headcount,
        is_baseline=data.get("is_baseline", False),
        results={
            "baseline": baseline,
            "salary_effect_applied": salary_effect,
            "assumption": (
                "Each 1% salary increase is assumed to reduce attrition by 0.4 "
                "percentage points. This is a stated assumption, not a measured "
                "elasticity."
            ),
        },
        created_by_id=actor_id,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return scenario
