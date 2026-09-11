"""Reusable pagination helpers."""

from math import ceil
from typing import Generic, List, Sequence, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class PaginationParams:
    """Query-string dependency: ?page=1&size=20"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number, starting at 1"),
        size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    ) -> None:
        self.page = page
        self.size = size
        self.offset = (page - 1) * size
        self.limit = size


class PageMeta(BaseModel):
    page: int
    size: int
    total: int
    pages: int
    has_next: bool
    has_prev: bool


class Page(BaseModel, Generic[T]):
    """Envelope returned by every list endpoint."""

    items: List[T] = Field(default_factory=list)
    meta: PageMeta

    @classmethod
    def create(cls, items: Sequence[T], total: int, params: PaginationParams) -> "Page[T]":
        pages = ceil(total / params.size) if params.size else 0
        return cls(
            items=list(items),
            meta=PageMeta(
                page=params.page,
                size=params.size,
                total=total,
                pages=pages,
                has_next=params.page < pages,
                has_prev=params.page > 1,
            ),
        )


def paginate(db: Session, stmt, params: PaginationParams):
    """Run a count query and a windowed query for the given select statement."""
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(stmt.offset(params.offset).limit(params.limit)).scalars().all()
    return rows, total
