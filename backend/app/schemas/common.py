"""Shared response shapes."""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ORMBase(BaseModel):
    """Base for schemas read from SQLAlchemy objects."""

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    success: bool = True
    message: str
    data: Optional[Any] = None


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    database: str
