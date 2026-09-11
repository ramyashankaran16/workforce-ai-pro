"""Department and designation schemas."""

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMBase


# ------------------------------------------------------------------ Department
class DepartmentBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = None
    location: Optional[str] = Field(None, max_length=150)
    budget: Optional[float] = Field(None, ge=0)
    headcount_limit: Optional[int] = Field(None, ge=0)


class DepartmentCreate(DepartmentBase):
    code: str = Field(..., min_length=2, max_length=30, pattern=r"^[A-Z0-9_-]+$")
    parent_id: Optional[int] = None
    head_employee_id: Optional[int] = None


class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    description: Optional[str] = None
    location: Optional[str] = Field(None, max_length=150)
    budget: Optional[float] = Field(None, ge=0)
    headcount_limit: Optional[int] = Field(None, ge=0)
    parent_id: Optional[int] = None
    head_employee_id: Optional[int] = None
    is_active: Optional[bool] = None


class DepartmentRead(ORMBase):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    budget: Optional[float] = None
    headcount_limit: Optional[int] = None
    parent_id: Optional[int] = None
    head_employee_id: Optional[int] = None
    is_active: bool


class DepartmentDetail(DepartmentRead):
    headcount: int = 0
    head_name: Optional[str] = None
    parent_name: Optional[str] = None


class DepartmentNode(DepartmentRead):
    """Nested representation for the org tree."""

    headcount: int = 0
    children: List["DepartmentNode"] = []


DepartmentNode.model_rebuild()


# ----------------------------------------------------------------- Designation
class DesignationBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = None
    level: int = Field(1, ge=1, le=20)
    min_salary: Optional[float] = Field(None, ge=0)
    max_salary: Optional[float] = Field(None, ge=0)


class DesignationCreate(DesignationBase):
    code: Optional[str] = Field(None, max_length=30)
    department_id: Optional[int] = None


class DesignationUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=120)
    description: Optional[str] = None
    level: Optional[int] = Field(None, ge=1, le=20)
    min_salary: Optional[float] = Field(None, ge=0)
    max_salary: Optional[float] = Field(None, ge=0)
    department_id: Optional[int] = None
    is_active: Optional[bool] = None


class DesignationRead(ORMBase):
    id: int
    code: Optional[str] = None
    title: str
    description: Optional[str] = None
    level: int
    min_salary: Optional[float] = None
    max_salary: Optional[float] = None
    department_id: Optional[int] = None
    is_active: bool
