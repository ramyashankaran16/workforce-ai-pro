"""
Cross-entity search.

`ILIKE '%term%'` cannot use a standard B-tree index, so it degrades linearly
with table size. That is acceptable at a few thousand employees and is not at
a few hundred thousand: the fix there is a PostgreSQL `tsvector` column with a
GIN index, which is noted as a known limitation rather than pretended away.

Results are permission-scoped, so search can never become a way to see records
the caller could not open directly.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.department import Department, Designation
from app.models.document import Document
from app.models.employee import Employee
from app.models.user import User
from app.models.workflow import Task
from app.services import employee_service

logger = logging.getLogger(__name__)

MIN_TERM_LENGTH = 2


def _pattern(term: str) -> str:
    return f"%{term.strip()}%"


def search_employees(
    db: Session, term: str, current_user: User, limit: int = 10
) -> List[dict]:
    pattern = _pattern(term)
    stmt = select(Employee).where(
        Employee.is_deleted.is_(False),
        or_(
            Employee.first_name.ilike(pattern),
            Employee.last_name.ilike(pattern),
            Employee.employee_code.ilike(pattern),
            Employee.work_email.ilike(pattern),
        ),
    )
    stmt = employee_service.scope_query(db, stmt, current_user).limit(limit)

    return [
        {
            "type": "employee",
            "id": row.id,
            "title": row.full_name,
            "subtitle": f"{row.employee_code} · {row.work_email}",
            "url": f"/employees/{row.id}",
        }
        for row in db.execute(stmt).scalars().all()
    ]


def search_departments(db: Session, term: str, limit: int = 5) -> List[dict]:
    pattern = _pattern(term)
    rows = (
        db.execute(
            select(Department)
            .where(
                Department.is_deleted.is_(False),
                or_(Department.name.ilike(pattern), Department.code.ilike(pattern)),
            )
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "type": "department",
            "id": row.id,
            "title": row.name,
            "subtitle": row.code,
            "url": f"/departments/{row.id}",
        }
        for row in rows
    ]


def search_designations(db: Session, term: str, limit: int = 5) -> List[dict]:
    pattern = _pattern(term)
    rows = (
        db.execute(
            select(Designation)
            .where(Designation.is_deleted.is_(False), Designation.title.ilike(pattern))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "type": "designation",
            "id": row.id,
            "title": row.title,
            "subtitle": f"Level {row.level}",
            "url": f"/designations/{row.id}",
        }
        for row in rows
    ]


def search_documents(
    db: Session, term: str, current_user: User, limit: int = 5
) -> List[dict]:
    from app.services import document_service

    pattern = _pattern(term)
    rows = (
        db.execute(
            select(Document)
            .where(Document.is_deleted.is_(False), Document.title.ilike(pattern))
            .limit(limit * 4)  # over-fetch, then filter by visibility
        )
        .scalars()
        .all()
    )
    visible = [d for d in rows if document_service.can_view(db, current_user, d)][:limit]
    return [
        {
            "type": "document",
            "id": row.id,
            "title": row.title,
            "subtitle": f"{row.file_type or 'file'} · {row.status.value}",
            "url": f"/documents/{row.id}",
        }
        for row in visible
    ]


def search_tasks(db: Session, term: str, current_user: User, limit: int = 5) -> List[dict]:
    pattern = _pattern(term)
    stmt = select(Task).where(
        Task.is_deleted.is_(False),
        or_(Task.title.ilike(pattern), Task.reference.ilike(pattern)),
    )
    role = (current_user.role_name or "").lower()
    if role not in {"admin", "hr"}:
        stmt = stmt.where(Task.assigned_to_id == current_user.id)

    rows = db.execute(stmt.limit(limit)).scalars().all()
    return [
        {
            "type": "task",
            "id": row.id,
            "title": row.title,
            "subtitle": f"{row.reference} · {row.status.value}",
            "url": f"/tasks/{row.id}",
        }
        for row in rows
    ]


def global_search(
    db: Session, term: str, current_user: User, limit_per_type: int = 5
) -> Dict[str, Any]:
    if len(term.strip()) < MIN_TERM_LENGTH:
        return {"term": term, "total": 0, "results": [], "note": "Term is too short."}

    results: List[dict] = []
    results += search_employees(db, term, current_user, limit_per_type)
    results += search_departments(db, term, limit_per_type)
    results += search_designations(db, term, limit_per_type)
    results += search_documents(db, term, current_user, limit_per_type)
    results += search_tasks(db, term, current_user, limit_per_type)

    return {
        "term": term,
        "total": len(results),
        "results": results,
        "by_type": {
            entity: sum(1 for r in results if r["type"] == entity)
            for entity in {r["type"] for r in results}
        },
    }


def suggest(db: Session, term: str, current_user: User, limit: int = 8) -> List[str]:
    """Type-ahead labels only."""
    if len(term.strip()) < MIN_TERM_LENGTH:
        return []
    items = search_employees(db, term, current_user, limit)
    items += search_departments(db, term, 3)
    return [item["title"] for item in items][:limit]
