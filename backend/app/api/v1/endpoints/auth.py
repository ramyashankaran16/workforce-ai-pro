"""Authentication endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions, get_current_user
from app.core.exceptions import PermissionDeniedError
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.common import MessageResponse
from app.schemas.user import UserCreate, UserCreatedResponse, UserProfile
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _client_info(request: Request):
    ip = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    return ip, request.headers.get("user-agent")


@router.post("/login", response_model=TokenResponse, summary="Log in with email and password")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip, agent = _client_info(request)
    user = auth_service.authenticate(db, payload.email, payload.password, ip, agent)
    access, refresh, expires_in = auth_service.issue_tokens(db, user, ip, agent)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=expires_in,
        user=UserProfile(**auth_service.build_profile_payload(db, user)),
    )


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="OAuth2 form login (used by the Swagger Authorize button)",
)
def login_form(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    ip, agent = _client_info(request)
    user = auth_service.authenticate(db, form.username, form.password, ip, agent)
    access, refresh, expires_in = auth_service.issue_tokens(db, user, ip, agent)
    return TokenResponse(access_token=access, refresh_token=refresh, expires_in=expires_in)


@router.post("/refresh", response_model=AccessTokenResponse, summary="Exchange a refresh token")
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    access, expires_in = auth_service.refresh_access_token(db, payload.refresh_token)
    return AccessTokenResponse(access_token=access, expires_in=expires_in)


@router.post("/logout", response_model=MessageResponse, summary="Revoke refresh tokens")
def logout(
    payload: LogoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.all_devices:
        count = auth_service.revoke_all_tokens(db, current_user.id)
        return MessageResponse(message=f"Signed out of {count} session(s).")
    if payload.refresh_token:
        auth_service.revoke_refresh_token(db, payload.refresh_token)
    return MessageResponse(message="Signed out.")


@router.get("/me", response_model=UserProfile, summary="Current user profile and permissions")
def read_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return UserProfile(**auth_service.build_profile_payload(db, current_user))


@router.post("/change-password", response_model=MessageResponse, summary="Change own password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    auth_service.change_password(
        db, current_user, payload.current_password, payload.new_password
    )
    return MessageResponse(message="Password changed. Please sign in again.")


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset another user's password (admin/HR)",
)
def reset_password(
    payload: ResetPasswordRequest,
    current_user: User = Depends(RequirePermissions("user:reset_password")),
    db: Session = Depends(get_db),
):
    if payload.user_id == current_user.id:
        raise PermissionDeniedError("Use /auth/change-password for your own account.")
    password = auth_service.reset_password(db, payload.user_id, payload.new_password)
    return MessageResponse(
        message="Password reset. The user must change it at next sign-in.",
        data={"temporary_password": password},
    )


@router.post(
    "/register",
    response_model=UserCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user account (admin/HR)",
)
def register(
    payload: UserCreate,
    _: User = Depends(RequirePermissions("user:create")),
    db: Session = Depends(get_db),
):
    user, temp_password = auth_service.create_user(
        db,
        email=payload.email,
        full_name=payload.full_name,
        role_name=payload.role_name,
        password=payload.password,
        phone=payload.phone,
        username=payload.username,
    )
    return UserCreatedResponse(user=user, temporary_password=temp_password)


@router.get("/permissions", summary="Permission codes held by the current user")
def my_permissions(current_user: User = Depends(get_current_user)):
    return {
        "role": current_user.role_name,
        "permissions": auth_service.permission_codes_for(current_user),
    }
