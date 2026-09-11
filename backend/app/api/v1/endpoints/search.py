"""Advanced search endpoints."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services import search_service

router = APIRouter(prefix="/search", tags=["Advanced Search"])


@router.get("", summary="Search across employees, departments, documents and tasks")
def global_search(
    q: str = Query(..., min_length=2, description="Search term"),
    limit_per_type: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Results are permission-scoped, so search can never surface a record the
    caller could not open directly.

    Known limitation: this uses `ILIKE '%term%'`, which cannot use a B-tree
    index and therefore degrades linearly with table size. At a few hundred
    thousand rows the answer is a PostgreSQL `tsvector` column with a GIN index.
    """
    return search_service.global_search(db, q, current_user, limit_per_type)


@router.get("/employees", summary="Employee search")
def employee_search(
    q: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    return search_service.search_employees(db, q, current_user, limit)


@router.get("/suggest", summary="Type-ahead suggestions")
def suggest(
    q: str = Query(..., min_length=2),
    limit: int = Query(8, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[str]:
    return search_service.suggest(db, q, current_user, limit)
