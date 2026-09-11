"""User administration endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.dependencies import RequirePermissions, get_current_user
from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate
from app.models.enums import UserStatus
from app.models.role import Role
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.user import UserRead, UserUpdate
from app.services import auth_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=Page[UserRead], summary="List users")
def list_users(
    params: PaginationParams = Depends(),
    search: Optional[str] = Query(None, description="Match name, email or username"),
    role: Optional[str] = Query(None, description="Filter by role name"),
    status_filter: Optional[UserStatus] = Query(None, alias="status"),
    _: User = Depends(RequirePermissions("user:read")),
    db: Session = Depends(get_db),
):
    stmt = (
        select(User)
        .options(selectinload(User.role))
        .where(User.is_deleted.is_(False))
    )

    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                User.full_name.ilike(pattern),
                User.email.ilike(pattern),
                User.username.ilike(pattern),
            )
        )
    if role:
        stmt = stmt.join(Role).where(Role.name == role.lower())
    if status_filter:
        stmt = stmt.where(User.status == status_filter)

    stmt = stmt.order_by(User.id.desc())
    rows, total = paginate(db, stmt, params)
    return Page[UserRead].create([UserRead.model_validate(r) for r in rows], total, params)


@router.get("/{user_id}", response_model=UserRead, summary="Get one user")
def get_user(
    user_id: int,
    _: User = Depends(RequirePermissions("user:read")),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise NotFoundError("User not found.")
    return user


@router.patch("/{user_id}", response_model=UserRead, summary="Update a user")
def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: User = Depends(RequirePermissions("user:update")),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise NotFoundError("User not found.")

    data = payload.model_dump(exclude_unset=True)

    if "role_name" in data and data["role_name"]:
        role = db.execute(
            select(Role).where(Role.name == data.pop("role_name").lower())
        ).scalar_one_or_none()
        if role is None:
            raise NotFoundError("Role not found.")
        if user.id == current_user.id and role.name != current_user.role_name:
            raise BusinessRuleError("You cannot change your own role.")
        user.role_id = role.id
    else:
        data.pop("role_name", None)

    if "status" in data and user.id == current_user.id:
        raise BusinessRuleError("You cannot change your own status.")

    for field, value in data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=MessageResponse, summary="Deactivate a user")
def deactivate_user(
    user_id: int,
    current_user: User = Depends(RequirePermissions("user:delete")),
    db: Session = Depends(get_db),
):
    if user_id == current_user.id:
        raise BusinessRuleError("You cannot deactivate your own account.")

    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise NotFoundError("User not found.")

    user.status = UserStatus.INACTIVE
    db.commit()
    auth_service.revoke_all_tokens(db, user.id)
    return MessageResponse(message=f"User {user.email} deactivated.")


@router.post("/{user_id}/activate", response_model=UserRead, summary="Reactivate a user")
def activate_user(
    user_id: int,
    _: User = Depends(RequirePermissions("user:update")),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise NotFoundError("User not found.")
    user.status = UserStatus.ACTIVE
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    db.refresh(user)
    return user
