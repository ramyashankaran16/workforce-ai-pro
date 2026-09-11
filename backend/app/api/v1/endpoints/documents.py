"""Document vault endpoints."""

import os
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import (
    RequirePermissions,
    get_current_employee,
    get_current_user,
)
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.pagination import Page, PaginationParams, paginate
from app.models.document import Document, DocumentCategory
from app.models.employee import Employee
from app.models.enums import DocumentStatus, DocumentVisibility
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.document import (
    ComplianceReport,
    DocumentCategoryCreate,
    DocumentCategoryRead,
    DocumentRead,
    DocumentVerify,
    ExpiringDocument,
)
from app.services import document_service, employee_service

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get(
    "/categories",
    response_model=List[DocumentCategoryRead],
    summary="Document categories",
)
def list_categories(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.execute(
            select(DocumentCategory)
            .where(DocumentCategory.is_active.is_(True))
            .order_by(DocumentCategory.name)
        )
        .scalars()
        .all()
    )


@router.post(
    "/categories",
    response_model=DocumentCategoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a category",
)
def create_category(
    payload: DocumentCategoryCreate,
    _: User = Depends(RequirePermissions("document:verify")),
    db: Session = Depends(get_db),
):
    category = DocumentCategory(**payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.post(
    "",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    employee_id: Optional[int] = Form(
        None, description="HR only; omit to upload against your own record."
    ),
    category_id: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    visibility: DocumentVisibility = Form(DocumentVisibility.HR_ONLY),
    issue_date: Optional[date] = Form(None),
    expiry_date: Optional[date] = Form(None),
    current_user: User = Depends(RequirePermissions("document:upload")),
    db: Session = Depends(get_db),
):
    """
    Validation goes beyond the extension: size, a blocked-extension list, a
    double-extension check, and magic bytes confirming the content matches the
    claimed type. Renaming a script to .pdf does not get it through.
    """
    target_id = employee_id
    if target_id is None:
        profile = employee_service.get_by_user(db, current_user.id)
        if profile is None:
            raise PermissionDeniedError(
                "No employee profile is linked to your account."
            )
        target_id = profile.id
    elif (current_user.role_name or "").lower() not in {"admin", "hr"}:
        raise PermissionDeniedError("Only HR can upload against another employee.")

    content = await file.read()
    return document_service.upload(
        db,
        employee_id=target_id,
        content=content,
        filename=file.filename or "upload",
        title=title,
        category_id=category_id,
        description=description,
        visibility=visibility,
        issue_date=issue_date,
        expiry_date=expiry_date,
        uploaded_by_id=current_user.id,
    )


@router.get("/me", response_model=Page[DocumentRead], summary="Own documents")
def my_documents(
    params: PaginationParams = Depends(),
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Document)
        .where(Document.employee_id == employee.id, Document.is_deleted.is_(False))
        .order_by(Document.id.desc())
    )
    rows, total = paginate(db, stmt, params)
    return Page[DocumentRead].create(
        [DocumentRead.model_validate(r) for r in rows], total, params
    )


@router.get("", response_model=Page[DocumentRead], summary="List documents (scoped)")
def list_documents(
    params: PaginationParams = Depends(),
    employee_id: Optional[int] = Query(None),
    category_id: Optional[int] = Query(None),
    status_filter: Optional[DocumentStatus] = Query(None, alias="status"),
    current_user: User = Depends(RequirePermissions("document:read_all")),
    db: Session = Depends(get_db),
):
    stmt = select(Document).where(Document.is_deleted.is_(False))
    if employee_id is not None:
        stmt = stmt.where(Document.employee_id == employee_id)
    if category_id is not None:
        stmt = stmt.where(Document.category_id == category_id)
    if status_filter:
        stmt = stmt.where(Document.status == status_filter)

    stmt = stmt.order_by(Document.id.desc())
    rows, total = paginate(db, stmt, params)
    return Page[DocumentRead].create(
        [DocumentRead.model_validate(r) for r in rows], total, params
    )


@router.get(
    "/expiring",
    response_model=List[ExpiringDocument],
    summary="Documents nearing expiry",
)
def expiring(
    days: int = Query(30, ge=1, le=365),
    _: User = Depends(RequirePermissions("document:read_all")),
    db: Session = Depends(get_db),
):
    return document_service.expiring_soon(db, days)


@router.get(
    "/compliance/{employee_id}",
    response_model=ComplianceReport,
    summary="Mandatory documents still missing",
)
def compliance(
    employee_id: int,
    current_user: User = Depends(RequirePermissions("document:read_all")),
    db: Session = Depends(get_db),
):
    employee = employee_service.get_employee(db, employee_id)
    missing = document_service.missing_mandatory(db, employee_id)
    return {
        "employee_id": employee.id,
        "employee_code": employee.employee_code,
        "employee_name": employee.full_name,
        "missing_mandatory": missing,
        "is_compliant": not missing,
    }


@router.get("/{document_id}", response_model=DocumentRead, summary="Document metadata")
def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = document_service.get_document(db, document_id)
    document_service.assert_can_view(db, current_user, document)
    return document


@router.get(
    "/{document_id}/download",
    summary="Download the file",
    response_class=FileResponse,
)
def download(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Served through the API rather than from the static mount, so the visibility
    rules are actually enforced. A file under /uploads would be readable by
    anyone who guessed the path.
    """
    document = document_service.get_document(db, document_id)
    document_service.assert_can_view(db, current_user, document)

    if not os.path.exists(document.file_path):
        raise NotFoundError("The stored file is missing from disk.")

    return FileResponse(
        document.file_path,
        filename=document.file_name,
        media_type="application/octet-stream",
    )


@router.post(
    "/{document_id}/verify",
    response_model=DocumentRead,
    summary="Verify or reject",
)
def verify(
    document_id: int,
    payload: DocumentVerify,
    current_user: User = Depends(RequirePermissions("document:verify")),
    db: Session = Depends(get_db),
):
    return document_service.verify(
        db, document_id, current_user.id, payload.approve, payload.reason
    )


@router.delete("/{document_id}", response_model=MessageResponse, summary="Delete")
def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = document_service.get_document(db, document_id)
    role = (current_user.role_name or "").lower()
    if role not in {"admin", "hr"}:
        profile = employee_service.get_by_user(db, current_user.id)
        if profile is None or document.employee_id != profile.id:
            raise PermissionDeniedError("You can only delete your own documents.")

    document_service.soft_delete(db, document_id)
    return MessageResponse(message="Document deleted.")
