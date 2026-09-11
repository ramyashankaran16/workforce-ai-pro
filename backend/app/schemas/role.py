"""Role and permission schemas."""

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMBase


class PermissionRead(ORMBase):
    id: int
    code: str
    name: str
    module: str
    description: Optional[str] = None


class RoleBase(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    hierarchy_level: int = Field(99, ge=1, le=99)


class RoleCreate(RoleBase):
    name: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    permission_codes: List[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = None
    hierarchy_level: Optional[int] = Field(None, ge=1, le=99)
    is_active: Optional[bool] = None


class RoleRead(ORMBase):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    hierarchy_level: int
    is_system_role: bool
    is_active: bool


class RoleWithPermissions(RoleRead):
    permissions: List[PermissionRead] = []


class PermissionAssign(BaseModel):
    permission_codes: List[str] = Field(..., min_length=1)
