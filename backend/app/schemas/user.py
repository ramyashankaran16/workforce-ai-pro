"""User schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import UserStatus
from app.schemas.common import ORMBase
from app.schemas.role import RoleRead


def validate_password_strength(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password must be 72 bytes or fewer.")
    if not any(c.isupper() for c in value):
        raise ValueError("Password must contain an uppercase letter.")
    if not any(c.islower() for c in value):
        raise ValueError("Password must contain a lowercase letter.")
    if not any(c.isdigit() for c in value):
        raise ValueError("Password must contain a digit.")
    return value


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=150)
    phone: Optional[str] = Field(None, max_length=20)
    username: Optional[str] = Field(None, max_length=80)


class UserCreate(UserBase):
    password: Optional[str] = Field(
        None, description="Omit to have a temporary password generated."
    )
    role_name: str = Field(..., description="admin | hr | manager | employee")

    @field_validator("password")
    @classmethod
    def check_password(cls, v: Optional[str]) -> Optional[str]:
        return validate_password_strength(v) if v else v


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=150)
    phone: Optional[str] = Field(None, max_length=20)
    avatar_url: Optional[str] = Field(None, max_length=500)
    status: Optional[UserStatus] = None
    role_name: Optional[str] = None


class UserRead(ORMBase):
    id: int
    email: EmailStr
    username: Optional[str] = None
    full_name: str
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    status: UserStatus
    is_email_verified: bool
    must_change_password: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    role: Optional[RoleRead] = None


class UserProfile(UserRead):
    """Returned by /auth/me - includes resolved permissions."""

    permissions: List[str] = []
    employee_id: Optional[int] = None
    employee_code: Optional[str] = None


class UserCreatedResponse(BaseModel):
    user: UserRead
    temporary_password: Optional[str] = Field(
        None, description="Present only when the password was auto-generated."
    )
