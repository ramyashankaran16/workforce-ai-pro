"""Dataset management endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.core.exceptions import ValidationError
from app.core.pagination import Page, PaginationParams, paginate
from app.models.dataset import Dataset
from app.models.enums import DatasetStatus
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.dataset import (
    DatasetDetail,
    DatasetPreview,
    DatasetRead,
    ValidationReport,
)
from app.services import dataset_service

router = APIRouter(prefix="/datasets", tags=["Datasets"])

ALLOWED_SUFFIXES = (".csv", ".xlsx", ".xls")


@router.get("", response_model=Page[DatasetRead], summary="List datasets")
def list_datasets(
    params: PaginationParams = Depends(),
    status_filter: Optional[DatasetStatus] = Query(None, alias="status"),
    _: User = Depends(RequirePermissions("dataset:manage")),
    db: Session = Depends(get_db),
):
    stmt = select(Dataset).where(Dataset.is_deleted.is_(False))
    if status_filter:
        stmt = stmt.where(Dataset.status == status_filter)
    stmt = stmt.order_by(Dataset.id.desc())

    rows, total = paginate(db, stmt, params)
    return Page[DatasetRead].create(
        [DatasetRead.model_validate(r) for r in rows], total, params
    )


@router.post(
    "/upload",
    response_model=DatasetDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and profile a dataset",
)
async def upload_dataset(
    file: UploadFile = File(..., description="CSV or Excel with a header row"),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    target_column: Optional[str] = Form(
        None, description="The label column, e.g. Attrition"
    ),
    current_user: User = Depends(RequirePermissions("dataset:manage")),
    db: Session = Depends(get_db),
):
    """
    Every column is profiled on upload: inferred type, null count, cardinality,
    and either summary statistics or the top categories.
    """
    filename = file.filename or ""
    if not filename.lower().endswith(ALLOWED_SUFFIXES):
        raise ValidationError("Only .csv, .xlsx and .xls files are accepted.")

    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise ValidationError(f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB.")

    dataset = dataset_service.create_dataset(
        db,
        content=content,
        filename=filename,
        name=name,
        description=description,
        target_column=target_column,
        uploaded_by_id=current_user.id,
    )
    return dataset


@router.get("/{dataset_id}", response_model=DatasetDetail, summary="Dataset profile")
def get_dataset(
    dataset_id: int,
    _: User = Depends(RequirePermissions("dataset:manage")),
    db: Session = Depends(get_db),
):
    return dataset_service.get_dataset(db, dataset_id)


@router.get(
    "/{dataset_id}/preview", response_model=DatasetPreview, summary="First N rows"
)
def preview_dataset(
    dataset_id: int,
    rows: int = Query(10, ge=1, le=50),
    _: User = Depends(RequirePermissions("dataset:manage")),
    db: Session = Depends(get_db),
):
    return dataset_service.preview(db, dataset_id, rows)


@router.post(
    "/{dataset_id}/validate",
    response_model=ValidationReport,
    summary="Run quality checks",
)
def validate_dataset(
    dataset_id: int,
    _: User = Depends(RequirePermissions("dataset:manage")),
    db: Session = Depends(get_db),
):
    """
    Reports every problem at once rather than failing on the first, so the file
    can be fixed in one pass.
    """
    return dataset_service.validate_dataset(db, dataset_id)


@router.delete("/{dataset_id}", response_model=MessageResponse, summary="Delete")
def delete_dataset(
    dataset_id: int,
    _: User = Depends(RequirePermissions("dataset:manage")),
    db: Session = Depends(get_db),
):
    dataset_service.soft_delete(db, dataset_id)
    return MessageResponse(message="Dataset deleted.")
