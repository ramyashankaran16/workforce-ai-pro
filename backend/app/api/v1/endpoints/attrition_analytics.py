"""Attrition analytics dashboard endpoints."""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.models.user import User
from app.schemas.analytics import (
    AttritionOverview,
    CohortRetention,
    DepartmentAttrition,
    ExitReason,
    ModelDrivers,
    RiskDistribution,
    TenureAttrition,
)
from app.services import analytics_service

router = APIRouter(prefix="/analytics/attrition", tags=["Attrition Analytics"])


@router.get("/overview", response_model=AttritionOverview, summary="Headline figures and trend")
def overview(
    months: int = Query(12, ge=3, le=36),
    _: User = Depends(RequirePermissions("analytics:read_all")),
    db: Session = Depends(get_db),
):
    """
    Voluntary and involuntary exits are reported separately. A termination is
    the company's decision, so lumping the two together hides which number the
    business can actually influence.
    """
    return analytics_service.overview(db, months)


@router.get(
    "/by-department",
    response_model=List[DepartmentAttrition],
    summary="Attrition rate per department",
)
def by_department(
    months: int = Query(12, ge=3, le=36),
    _: User = Depends(RequirePermissions("analytics:read_all")),
    db: Session = Depends(get_db),
):
    return analytics_service.by_department(db, months)


@router.get(
    "/by-tenure",
    response_model=List[TenureAttrition],
    summary="Attrition by tenure band",
)
def by_tenure(
    _: User = Depends(RequirePermissions("analytics:read_all")),
    db: Session = Depends(get_db),
):
    """
    The first year usually dominates. Split this way, "we have an attrition
    problem" often turns out to be "we have an onboarding problem".
    """
    return analytics_service.by_tenure(db)


@router.get("/exit-reasons", response_model=List[ExitReason], summary="Stated exit reasons")
def exit_reasons(
    limit: int = Query(10, ge=1, le=50),
    _: User = Depends(RequirePermissions("analytics:read_all")),
    db: Session = Depends(get_db),
):
    return analytics_service.exit_reasons(db, limit)


@router.get("/drivers", response_model=ModelDrivers, summary="Model feature importance")
def drivers(
    _: User = Depends(RequirePermissions("analytics:read_all")),
    db: Session = Depends(get_db),
):
    return analytics_service.model_drivers(db)


@router.get(
    "/risk-distribution",
    response_model=RiskDistribution,
    summary="How the workforce splits across risk bands",
)
def risk_distribution(
    _: User = Depends(RequirePermissions("analytics:read_all")),
    db: Session = Depends(get_db),
):
    return analytics_service.risk_distribution(db)


@router.get(
    "/cohort",
    response_model=List[CohortRetention],
    summary="Retention by joining cohort",
)
def cohort(
    months: int = Query(12, ge=3, le=36),
    _: User = Depends(RequirePermissions("analytics:read_all")),
    db: Session = Depends(get_db),
):
    return analytics_service.cohort_retention(db, months)
