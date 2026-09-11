"""Workforce Stability Engine endpoints."""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.models.user import User
from app.schemas.stability import (
    DepartmentStability,
    StabilityDetail,
    StabilitySnapshotRead,
)
from app.services import stability_service

router = APIRouter(prefix="/stability", tags=["Workforce Stability"])


@router.get("", response_model=StabilityDetail, summary="Latest stability index")
def latest(
    department_id: Optional[int] = Query(None),
    _: User = Depends(RequirePermissions("stability:read")),
    db: Session = Depends(get_db),
):
    """
    A single index is only useful if it can be taken apart, so every metric is
    returned with its raw value, normalised score, weight and benchmark.

    The weights are a stated judgement, not a discovered truth. They are
    returned with every snapshot rather than hidden in the code.
    """
    snapshot = stability_service.latest(db, department_id)
    payload = {c.name: getattr(snapshot, c.name) for c in snapshot.__table__.columns}
    payload["metrics"] = snapshot.metrics
    return payload


@router.get(
    "/history",
    response_model=List[StabilitySnapshotRead],
    summary="Index over time",
)
def history(
    department_id: Optional[int] = Query(None),
    limit: int = Query(12, ge=1, le=60),
    _: User = Depends(RequirePermissions("stability:read")),
    db: Session = Depends(get_db),
):
    return stability_service.history(db, department_id, limit)


@router.post(
    "/snapshot",
    response_model=StabilityDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Compute a new snapshot",
)
def snapshot(
    department_id: Optional[int] = Query(None),
    _: User = Depends(RequirePermissions("stability:read")),
    db: Session = Depends(get_db),
):
    """Re-running on the same date replaces that day's snapshot rather than stacking."""
    record = stability_service.compute_snapshot(db, department_id)
    payload = {c.name: getattr(record, c.name) for c in record.__table__.columns}
    payload["metrics"] = record.metrics
    return payload


@router.get(
    "/compare",
    response_model=List[DepartmentStability],
    summary="Department comparison",
)
def compare(
    _: User = Depends(RequirePermissions("stability:read")),
    db: Session = Depends(get_db),
):
    return stability_service.compare_departments(db)
