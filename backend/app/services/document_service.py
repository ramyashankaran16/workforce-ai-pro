"""Document vault: upload validation, verification workflow and expiry scanning."""

import logging
import os
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
)
from app.models.document import Document, DocumentCategory
from app.models.employee import Employee
from app.models.enums import (
    DocumentStatus,
    DocumentVisibility,
    NotificationCategory,
    NotificationType,
    Priority,
)
from app.models.user import User
from app.services import employee_service, notification_service
from app.utils import file_handler
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)

DOCUMENT_DIR = os.path.join(settings.UPLOAD_DIR, "documents")
DEFAULT_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "docx"}


def get_category(db: Session, category_id: int) -> DocumentCategory:
    category = db.get(DocumentCategory, category_id)
    if category is None:
        raise NotFoundError("Document category not found.")
    return category


def get_document(db: Session, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.is_deleted:
        raise NotFoundError("Document not found.")
    return document


def can_view(db: Session, user: User, document: Document) -> bool:
    """
    Visibility is the document's own setting, layered on top of role.

    A payslip marked private is readable by its owner and HR, not by the line
    manager -- which is the point of having the field at all.
    """
    role = (user.role_name or "").lower()
    if role in {"admin", "hr"}:
        return True

    profile = employee_service.get_by_user(db, user.id)
    if profile is None:
        return False

    is_owner = document.employee_id == profile.id
    if document.visibility == DocumentVisibility.PUBLIC:
        return True
    if document.visibility == DocumentVisibility.HR_ONLY:
        return is_owner
    if document.visibility == DocumentVisibility.PRIVATE:
        return is_owner
    if document.visibility == DocumentVisibility.MANAGER:
        if is_owner:
            return True
        owner = db.get(Employee, document.employee_id)
        return bool(owner and owner.manager_id == profile.id)
    return False


def assert_can_view(db: Session, user: User, document: Document) -> None:
    if not can_view(db, user, document):
        raise PermissionDeniedError("You do not have access to this document.")


def upload(
    db: Session,
    employee_id: int,
    content: bytes,
    filename: str,
    title: str,
    category_id: Optional[int] = None,
    description: Optional[str] = None,
    visibility: DocumentVisibility = DocumentVisibility.HR_ONLY,
    issue_date: Optional[date] = None,
    expiry_date: Optional[date] = None,
    uploaded_by_id: Optional[int] = None,
) -> Document:
    employee = db.get(Employee, employee_id)
    if employee is None or employee.is_deleted:
        raise NotFoundError("Employee not found.")

    allowed = DEFAULT_EXTENSIONS
    max_size = settings.MAX_UPLOAD_SIZE_MB
    category = None
    if category_id:
        category = get_category(db, category_id)
        allowed = {
            e.strip().lower()
            for e in (category.allowed_extensions or "").split(",")
            if e.strip()
        } or DEFAULT_EXTENSIONS
        max_size = category.max_size_mb or max_size

        if category.requires_expiry and expiry_date is None:
            raise BusinessRuleError(f"{category.name} requires an expiry date.")

    if expiry_date and issue_date and expiry_date <= issue_date:
        raise BusinessRuleError("The expiry date must be after the issue date.")

    extension = file_handler.validate_upload(content, filename, allowed, max_size)
    path, size = file_handler.write_file(content, DOCUMENT_DIR, filename)

    # A re-upload in the same category supersedes the previous version.
    version = 1
    if category_id:
        previous = db.execute(
            select(func.max(Document.version)).where(
                Document.employee_id == employee_id,
                Document.category_id == category_id,
                Document.is_deleted.is_(False),
            )
        ).scalar()
        version = (previous or 0) + 1

    document = Document(
        employee_id=employee_id,
        category_id=category_id,
        title=title,
        description=description,
        file_name=file_handler.safe_filename(filename),
        file_path=path,
        file_type=extension,
        file_size=size,
        version=version,
        status=DocumentStatus.PENDING,
        visibility=visibility,
        issue_date=issue_date,
        expiry_date=expiry_date,
        uploaded_by_id=uploaded_by_id,
    )
    db.add(document)
    db.flush()

    notification_service.notify_roles(
        db,
        ["hr"],
        title="Document awaiting verification",
        message=f"{employee.full_name} uploaded '{title}'.",
        category=NotificationCategory.DOCUMENT,
        reference_type="document",
        reference_id=document.id,
        action_url=f"/documents/{document.id}",
    )

    db.commit()
    db.refresh(document)
    return document


def verify(
    db: Session, document_id: int, verified_by_id: int, approve: bool,
    reason: Optional[str] = None,
) -> Document:
    document = get_document(db, document_id)
    if document.status == DocumentStatus.VERIFIED and approve:
        raise BusinessRuleError("That document is already verified.")
    if not approve and not reason:
        raise BusinessRuleError("A rejection needs a reason.")

    document.status = DocumentStatus.VERIFIED if approve else DocumentStatus.REJECTED
    document.verified_by_id = verified_by_id
    document.verified_at = utcnow()
    document.rejection_reason = None if approve else reason

    employee = db.get(Employee, document.employee_id)
    if employee and employee.user_id:
        notification_service.notify(
            db,
            employee.user_id,
            title=f"Document {document.status.value}",
            message=(
                f"'{document.title}' was verified."
                if approve
                else f"'{document.title}' was rejected: {reason}"
            ),
            category=NotificationCategory.DOCUMENT,
            notification_type=(
                NotificationType.SUCCESS if approve else NotificationType.WARNING
            ),
            reference_type="document",
            reference_id=document.id,
            commit=False,
        )

    db.commit()
    db.refresh(document)
    return document


def soft_delete(db: Session, document_id: int) -> None:
    document = get_document(db, document_id)
    document.is_deleted = True
    document.deleted_at = utcnow()
    db.commit()


def expiring_soon(db: Session, days: int = 30) -> List[dict]:
    cutoff = date.today() + timedelta(days=days)
    rows = (
        db.execute(
            select(Document, Employee)
            .join(Employee, Employee.id == Document.employee_id)
            .where(
                Document.is_deleted.is_(False),
                Document.expiry_date.isnot(None),
                Document.expiry_date <= cutoff,
                Document.status != DocumentStatus.REJECTED,
            )
            .order_by(Document.expiry_date)
        )
        .all()
    )

    out = []
    for document, employee in rows:
        remaining = (document.expiry_date - date.today()).days
        out.append(
            {
                "document_id": document.id,
                "title": document.title,
                "employee_id": employee.id,
                "employee_code": employee.employee_code,
                "employee_name": employee.full_name,
                "expiry_date": document.expiry_date,
                "days_remaining": remaining,
                "already_expired": remaining < 0,
            }
        )
    return out


def flag_expired(db: Session) -> int:
    """Nightly pass: move anything past its expiry into the expired state."""
    rows = (
        db.execute(
            select(Document).where(
                Document.is_deleted.is_(False),
                Document.expiry_date.isnot(None),
                Document.expiry_date < date.today(),
                Document.status != DocumentStatus.EXPIRED,
            )
        )
        .scalars()
        .all()
    )
    for document in rows:
        document.status = DocumentStatus.EXPIRED
        employee = db.get(Employee, document.employee_id)
        if employee and employee.user_id:
            notification_service.notify(
                db,
                employee.user_id,
                title="Document expired",
                message=f"'{document.title}' expired on {document.expiry_date}.",
                category=NotificationCategory.DOCUMENT,
                notification_type=NotificationType.WARNING,
                priority=Priority.HIGH,
                reference_type="document",
                reference_id=document.id,
                commit=False,
            )
    db.commit()
    return len(rows)


def missing_mandatory(db: Session, employee_id: int) -> List[str]:
    """Mandatory categories with no verified document on file."""
    mandatory = (
        db.execute(
            select(DocumentCategory).where(
                DocumentCategory.is_mandatory.is_(True),
                DocumentCategory.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )
    held = {
        row
        for row in db.execute(
            select(Document.category_id).where(
                Document.employee_id == employee_id,
                Document.is_deleted.is_(False),
                Document.status == DocumentStatus.VERIFIED,
            )
        ).scalars().all()
    }
    return [c.name for c in mandatory if c.id not in held]
