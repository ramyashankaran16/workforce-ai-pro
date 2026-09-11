"""Authentication request and response schemas."""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import UserProfile, validate_password_strength


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token lifetime in seconds")
    user: Optional[UserProfile] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_new_password(cls, v: str) -> str:
        return validate_password_strength(v)


class ResetPasswordRequest(BaseModel):
    user_id: int
    new_password: Optional[str] = None

    @field_validator("new_password")
    @classmethod
    def check_new_password(cls, v: Optional[str]) -> Optional[str]:
        return validate_password_strength(v) if v else v


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None
    all_devices: bool = False
