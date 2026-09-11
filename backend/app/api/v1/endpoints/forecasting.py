"""Workforce forecasting endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.core.pagination import Page, PaginationParams, paginate
from app.models.enums import ForecastType
from app.models.forecast import ForecastScenario, WorkforceForecast
from app.models.user import User
from app.schemas.forecast import (
    ForecastCreate,
    ForecastDetail,
    ForecastRead,
    ScenarioCreate,
    ScenarioRead,
)
from app.services import forecast_service

router = APIRouter(prefix="/forecasting", tags=["Workforce Forecasting"])


@router.get("", response_model=Page[ForecastRead], summary="List forecasts")
def list_forecasts(
    params: PaginationParams = Depends(),
    forecast_type: Optional[ForecastType] = Query(None),
    _: User = Depends(RequirePermissions("forecast:manage")),
    db: Session = Depends(get_db),
):
    stmt = select(WorkforceForecast)
    if forecast_type:
        stmt = stmt.where(WorkforceForecast.forecast_type == forecast_type)
    stmt = stmt.order_by(WorkforceForecast.id.desc())

    rows, total = paginate(db, stmt, params)
    return Page[ForecastRead].create(
        [ForecastRead.model_validate(r) for r in rows], total, params
    )


@router.post(
    "",
    response_model=ForecastDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a forecast",
)
def create_forecast(
    payload: ForecastCreate,
    current_user: User = Depends(RequirePermissions("forecast:manage")),
    db: Session = Depends(get_db),
):
    """
    Ordinary least squares over the monthly history, with prediction intervals
    derived from the residual standard error. The interval widens further out,
    which is the honest shape.

    With fewer than four historical periods the method falls back to the mean
    rather than extrapolating a trend from three points.
    """
    forecast = forecast_service.create_forecast(
        db,
        name=payload.name,
        forecast_type=payload.forecast_type,
        horizon_periods=payload.horizon_periods,
        lookback_periods=payload.lookback_periods,
        department_id=payload.department_id,
        confidence=payload.confidence,
        description=payload.description,
        actor_id=current_user.id,
    )
    return _detail(db, forecast)


@router.get("/{forecast_id}", response_model=ForecastDetail, summary="Forecast with points")
def get_forecast(
    forecast_id: int,
    _: User = Depends(RequirePermissions("forecast:manage")),
    db: Session = Depends(get_db),
):
    return _detail(db, forecast_service.get_forecast(db, forecast_id))


@router.post(
    "/{forecast_id}/scenarios",
    response_model=ScenarioRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a what-if scenario",
)
def create_scenario(
    forecast_id: int,
    payload: ScenarioCreate,
    current_user: User = Depends(RequirePermissions("forecast:manage")),
    db: Session = Depends(get_db),
):
    """
    The adjustments are applied arithmetically to the projection; the model is
    not re-fitted. The salary-to-attrition elasticity is a stated assumption
    returned in `results`, not a measured effect.
    """
    return forecast_service.create_scenario(
        db, forecast_id, payload.model_dump(), actor_id=current_user.id
    )


@router.get(
    "/{forecast_id}/scenarios",
    response_model=List[ScenarioRead],
    summary="Compare scenarios",
)
def list_scenarios(
    forecast_id: int,
    _: User = Depends(RequirePermissions("forecast:manage")),
    db: Session = Depends(get_db),
):
    forecast_service.get_forecast(db, forecast_id)
    return (
        db.execute(
            select(ForecastScenario).where(ForecastScenario.forecast_id == forecast_id)
        )
        .scalars()
        .all()
    )


def _detail(db: Session, forecast: WorkforceForecast) -> dict:
    payload = {c.name: getattr(forecast, c.name) for c in forecast.__table__.columns}
    payload["data_points"] = sorted(
        forecast.data_points, key=lambda p: p.period_date
    )
    return payload
