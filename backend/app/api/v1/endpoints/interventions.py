"""HR intervention and decision-support endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.core.pagination import Page, PaginationParams, paginate
from app.models.employee import Employee
from app.models.enums import InterventionStatus, InterventionType
from app.models.intervention import InterventionAction, InterventionPlan
from app.models.user import User
from app.schemas.intervention import (
    ActionComplete,
    ActionCreate,
    ActionRead,
    EffectivenessReport,
    InterventionCreate,
    InterventionDetail,
    InterventionRead,
    InterventionUpdate,
)
from app.services import employee_service, intervention_service

router = APIRouter(prefix="/interventions", tags=["HR Interventions"])


@router.get("", response_model=Page[InterventionRead], summary="List plans (scoped)")
def list_plans(
    params: PaginationParams = Depends(),
    status_filter: Optional[InterventionStatus] = Query(None, alias="status"),
    intervention_type: Optional[InterventionType] = Query(None),
    employee_id: Optional[int] = Query(None),
    current_user: User = Depends(RequirePermissions("intervention:manage")),
    db: Session = Depends(get_db),
):
    visible_ids = db.execute(
        employee_service.scope_query(db, select(Employee.id), current_user)
    ).scalars().all()

    stmt = select(InterventionPlan).where(
        InterventionPlan.employee_id.in_(visible_ids)
    )
    if status_filter:
        stmt = stmt.where(InterventionPlan.status == status_filter)
    if intervention_type:
        stmt = stmt.where(InterventionPlan.intervention_type == intervention_type)
    if employee_id is not None:
        stmt = stmt.where(InterventionPlan.employee_id == employee_id)

    stmt = stmt.order_by(InterventionPlan.start_date.desc())
    rows, total = paginate(db, stmt, params)
    return Page[InterventionRead].create(
        [InterventionRead.model_validate(r) for r in rows], total, params
    )


@router.get(
    "/effectiveness",
    response_model=EffectivenessReport,
    summary="Before/after comparison across completed plans",
)
def effectiveness(
    _: User = Depends(RequirePermissions("intervention:manage")),
    db: Session = Depends(get_db),
):
    """
    Reports observed change, not proven effect. High risk scores drift toward
    the mean on their own, and there is no control group here, so the `caveat`
    field is part of the response rather than a footnote.
    """
    return intervention_service.effectiveness(db)


@router.post(
    "",
    response_model=InterventionDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a retention plan",
)
def create_plan(
    payload: InterventionCreate,
    current_user: User = Depends(RequirePermissions("intervention:manage")),
    db: Session = Depends(get_db),
):
    """Captures the employee's current risk score as the before figure."""
    employee = employee_service.get_employee(db, payload.employee_id)
    employee_service.assert_can_access(db, current_user, employee)

    plan = intervention_service.create_plan(
        db, payload.model_dump(), actor_id=current_user.id
    )
    return _detail(db, plan)


@router.get("/{plan_id}", response_model=InterventionDetail, summary="Plan with actions")
def get_plan(
    plan_id: int,
    current_user: User = Depends(RequirePermissions("intervention:manage")),
    db: Session = Depends(get_db),
):
    plan = intervention_service.get_plan(db, plan_id)
    employee = employee_service.get_employee(db, plan.employee_id)
    employee_service.assert_can_access(db, current_user, employee)
    return _detail(db, plan)


@router.patch(
    "/{plan_id}", response_model=InterventionDetail, summary="Update status or outcome"
)
def update_plan(
    plan_id: int,
    payload: InterventionUpdate,
    current_user: User = Depends(RequirePermissions("intervention:manage")),
    db: Session = Depends(get_db),
):
    """Completing a plan requires every action to be closed first."""
    plan = intervention_service.update_plan(
        db, plan_id, payload.model_dump(exclude_unset=True)
    )
    return _detail(db, plan)


@router.post(
    "/{plan_id}/actions",
    response_model=ActionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add an action to a plan",
)
def add_action(
    plan_id: int,
    payload: ActionCreate,
    _: User = Depends(RequirePermissions("intervention:manage")),
    db: Session = Depends(get_db),
):
    return intervention_service.add_action(db, plan_id, payload.model_dump())


@router.post(
    "/actions/{action_id}/complete",
    response_model=ActionRead,
    summary="Mark an action complete",
)
def complete_action(
    action_id: int,
    payload: ActionComplete,
    _: User = Depends(RequirePermissions("intervention:manage")),
    db: Session = Depends(get_db),
):
    return intervention_service.complete_action(db, action_id, payload.notes)


def _detail(db: Session, plan: InterventionPlan) -> dict:
    employee = db.get(Employee, plan.employee_id)
    payload = {c.name: getattr(plan, c.name) for c in plan.__table__.columns}
    payload.update(
        {
            "employee_code": employee.employee_code if employee else None,
            "employee_name": employee.full_name if employee else None,
            "actions": sorted(plan.actions, key=lambda a: a.sequence),
        }
    )
    return payload
