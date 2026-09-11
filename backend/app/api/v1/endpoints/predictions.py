"""Attrition prediction endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PaginationParams, paginate
from app.models.employee import Employee
from app.models.enums import ModelStatus, PredictionSource, RiskLevel
from app.models.prediction import AttritionPrediction, ModelVersion, PredictionBatch
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.prediction import (
    BatchRead,
    ModelVersionDetail,
    ModelVersionRead,
    OutcomeRecord,
    PredictionDetail,
    PredictionRead,
    TrainRequest,
)
from app.ml import registry
from app.services import employee_service, prediction_service

router = APIRouter(prefix="/predictions", tags=["Attrition Prediction"])


# --------------------------------------------------------------------- models
@router.post(
    "/train",
    response_model=ModelVersionDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Train a new model version",
)
def train(
    payload: TrainRequest,
    current_user: User = Depends(RequirePermissions("model:train")),
    db: Session = Depends(get_db),
):
    """
    Trains on live employee data with leakage controls applied: exit date, exit
    reason and status are excluded, since they are only recorded because
    someone left.

    The response reports precision, recall and PR-AUC alongside a
    majority-class baseline. With attrition around 15%, accuracy alone is
    misleading -- predicting "nobody leaves" would score 85%.
    """
    return prediction_service.train_new_version(
        db,
        name=payload.name,
        algorithm=payload.algorithm,
        horizon_days=payload.horizon_days,
        voluntary_only=payload.voluntary_only,
        include_protected=payload.include_protected_attributes,
        decision_threshold=payload.decision_threshold,
        hyperparameters=payload.hyperparameters,
        dataset_id=payload.dataset_id,
        actor_id=current_user.id,
    )


@router.get(
    "/models", response_model=Page[ModelVersionRead], summary="List model versions"
)
def list_models(
    params: PaginationParams = Depends(),
    status_filter: Optional[ModelStatus] = Query(None, alias="status"),
    _: User = Depends(RequirePermissions("prediction:read")),
    db: Session = Depends(get_db),
):
    stmt = select(ModelVersion)
    if status_filter:
        stmt = stmt.where(ModelVersion.status == status_filter)
    stmt = stmt.order_by(ModelVersion.id.desc())

    rows, total = paginate(db, stmt, params)
    return Page[ModelVersionRead].create(
        [ModelVersionRead.model_validate(r) for r in rows], total, params
    )


@router.get(
    "/models/active",
    response_model=Optional[ModelVersionDetail],
    summary="Currently deployed model",
)
def active_model(
    _: User = Depends(RequirePermissions("prediction:read")),
    db: Session = Depends(get_db),
):
    return registry.deployed_model(db)


@router.get(
    "/models/{version_id}",
    response_model=ModelVersionDetail,
    summary="Model version with full evaluation report",
)
def get_model(
    version_id: int,
    _: User = Depends(RequirePermissions("prediction:read")),
    db: Session = Depends(get_db),
):
    version = db.get(ModelVersion, version_id)
    if version is None:
        raise NotFoundError("Model version not found.")
    return version


@router.post(
    "/models/{version_id}/deploy",
    response_model=ModelVersionDetail,
    summary="Make this version the active one",
)
def deploy_model(
    version_id: int,
    _: User = Depends(RequirePermissions("model:deploy")),
    db: Session = Depends(get_db),
):
    """Exactly one version can be active; the previous one is archived."""
    return registry.deploy(db, version_id)


# ---------------------------------------------------------------- predictions
@router.post(
    "/employee/{employee_id}",
    response_model=PredictionDetail,
    summary="Score one employee with an explanation",
)
def predict_employee(
    employee_id: int,
    explain: bool = Query(True, description="Include per-factor contributions"),
    current_user: User = Depends(RequirePermissions("prediction:run")),
    db: Session = Depends(get_db),
):
    """
    The explanation is produced by occlusion: each feature is replaced with the
    population's typical value and the model re-scored, so the contribution is
    measured from the model rather than inferred from global importance.
    """
    employee = employee_service.get_employee(db, employee_id)
    employee_service.assert_can_access(db, current_user, employee)

    record = prediction_service.predict_for_employee(
        db, employee_id, with_explanation=explain, source=PredictionSource.MANUAL
    )
    return _detail(db, record)


@router.post(
    "/batch",
    response_model=BatchRead,
    summary="Score every active employee",
)
def run_batch(
    current_user: User = Depends(RequirePermissions("prediction:run")),
    db: Session = Depends(get_db),
):
    """One vectorised pass over all employees rather than a loop of single calls."""
    return prediction_service.run_batch(db, actor_id=current_user.id)


@router.get("/batches", response_model=Page[BatchRead], summary="List batch runs")
def list_batches(
    params: PaginationParams = Depends(),
    _: User = Depends(RequirePermissions("prediction:read")),
    db: Session = Depends(get_db),
):
    stmt = select(PredictionBatch).order_by(PredictionBatch.id.desc())
    rows, total = paginate(db, stmt, params)
    return Page[BatchRead].create(
        [BatchRead.model_validate(r) for r in rows], total, params
    )


@router.get("", response_model=Page[PredictionRead], summary="List predictions")
def list_predictions(
    params: PaginationParams = Depends(),
    employee_id: Optional[int] = Query(None),
    risk_level: Optional[RiskLevel] = Query(None),
    batch_id: Optional[int] = Query(None),
    min_probability: Optional[float] = Query(None, ge=0, le=1),
    current_user: User = Depends(RequirePermissions("prediction:read")),
    db: Session = Depends(get_db),
):
    visible_ids = db.execute(
        employee_service.scope_query(db, select(Employee.id), current_user)
    ).scalars().all()

    stmt = select(AttritionPrediction).where(
        AttritionPrediction.employee_id.in_(visible_ids)
    )
    if employee_id is not None:
        stmt = stmt.where(AttritionPrediction.employee_id == employee_id)
    if risk_level:
        stmt = stmt.where(AttritionPrediction.risk_level == risk_level)
    if batch_id is not None:
        stmt = stmt.where(AttritionPrediction.batch_id == batch_id)
    if min_probability is not None:
        stmt = stmt.where(
            AttritionPrediction.attrition_probability >= min_probability
        )

    stmt = stmt.order_by(AttritionPrediction.attrition_probability.desc())
    rows, total = paginate(db, stmt, params)
    return Page[PredictionRead].create(
        [PredictionRead.model_validate(r) for r in rows], total, params
    )


@router.get(
    "/employee/{employee_id}/history",
    response_model=List[PredictionRead],
    summary="Prediction history for one employee",
)
def employee_history(
    employee_id: int,
    current_user: User = Depends(RequirePermissions("prediction:read")),
    db: Session = Depends(get_db),
):
    employee = employee_service.get_employee(db, employee_id)
    employee_service.assert_can_access(db, current_user, employee)

    return (
        db.execute(
            select(AttritionPrediction)
            .where(AttritionPrediction.employee_id == employee_id)
            .order_by(AttritionPrediction.predicted_at.desc())
        )
        .scalars()
        .all()
    )


@router.post(
    "/outcomes",
    response_model=MessageResponse,
    summary="Record what actually happened",
)
def record_outcome(
    payload: OutcomeRecord,
    _: User = Depends(RequirePermissions("prediction:run")),
    db: Session = Depends(get_db),
):
    """
    Stamps the real outcome onto past predictions. Without this the model can
    only ever be judged against its own test split, never against reality.
    """
    updated = prediction_service.record_actual_outcome(
        db, payload.employee_id, payload.left
    )
    return MessageResponse(message=f"Updated {updated} prediction(s).")


def _detail(db: Session, record: AttritionPrediction) -> dict:
    employee = db.get(Employee, record.employee_id)
    payload = {c.name: getattr(record, c.name) for c in record.__table__.columns}
    payload.update(
        {
            "employee_code": employee.employee_code if employee else None,
            "employee_name": employee.full_name if employee else None,
            "department_name": (
                employee.department.name if employee and employee.department else None
            ),
            "factors": (record.top_factors or {}).get("factors", []),
        }
    )
    return payload
