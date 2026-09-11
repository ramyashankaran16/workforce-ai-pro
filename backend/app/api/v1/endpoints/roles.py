"""Role and permission management endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.core.exceptions import BusinessRuleError, DuplicateError, NotFoundError
from app.models.role import Permission, Role
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.role import (
    PermissionAssign,
    PermissionRead,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    RoleWithPermissions,
)

router = APIRouter(prefix="/roles", tags=["Roles & Permissions"])


@router.get("", response_model=List[RoleRead], summary="List roles")
def list_roles(
    _: User = Depends(RequirePermissions("role:read")),
    db: Session = Depends(get_db),
):
    return (
        db.execute(select(Role).order_by(Role.hierarchy_level)).scalars().all()
    )


@router.get(
    "/permissions",
    response_model=List[PermissionRead],
    summary="List every permission",
)
def list_permissions(
    module: Optional[str] = Query(None, description="Filter by module"),
    _: User = Depends(RequirePermissions("role:read")),
    db: Session = Depends(get_db),
):
    stmt = select(Permission).order_by(Permission.module, Permission.code)
    if module:
        stmt = stmt.where(Permission.module == module.lower())
    return db.execute(stmt).scalars().all()


@router.get("/{role_id}", response_model=RoleWithPermissions, summary="Get a role")
def get_role(
    role_id: int,
    _: User = Depends(RequirePermissions("role:read")),
    db: Session = Depends(get_db),
):
    role = db.execute(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
    ).scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found.")
    return role


@router.post(
    "",
    response_model=RoleWithPermissions,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom role",
)
def create_role(
    payload: RoleCreate,
    _: User = Depends(RequirePermissions("role:manage")),
    db: Session = Depends(get_db),
):
    existing = db.execute(
        select(Role).where(Role.name == payload.name.lower())
    ).scalar_one_or_none()
    if existing:
        raise DuplicateError(f"Role '{payload.name}' already exists.")

    role = Role(
        name=payload.name.lower(),
        display_name=payload.display_name,
        description=payload.description,
        hierarchy_level=payload.hierarchy_level,
        is_system_role=False,
    )

    if payload.permission_codes:
        perms = (
            db.execute(select(Permission).where(Permission.code.in_(payload.permission_codes)))
            .scalars()
            .all()
        )
        found = {p.code for p in perms}
        missing = set(payload.permission_codes) - found
        if missing:
            raise NotFoundError(f"Unknown permission codes: {', '.join(sorted(missing))}")
        role.permissions = perms

    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.patch("/{role_id}", response_model=RoleRead, summary="Update a role")
def update_role(
    role_id: int,
    payload: RoleUpdate,
    _: User = Depends(RequirePermissions("role:manage")),
    db: Session = Depends(get_db),
):
    role = db.get(Role, role_id)
    if role is None:
        raise NotFoundError("Role not found.")
    if role.is_system_role and payload.is_active is False:
        raise BusinessRuleError("System roles cannot be deactivated.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(role, field, value)

    db.commit()
    db.refresh(role)
    return role


@router.put(
    "/{role_id}/permissions",
    response_model=RoleWithPermissions,
    summary="Replace a role's permissions",
)
def set_role_permissions(
    role_id: int,
    payload: PermissionAssign,
    _: User = Depends(RequirePermissions("role:manage")),
    db: Session = Depends(get_db),
):
    role = db.execute(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
    ).scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found.")
    if role.name == "admin":
        raise BusinessRuleError("The admin role always holds every permission.")

    perms = (
        db.execute(select(Permission).where(Permission.code.in_(payload.permission_codes)))
        .scalars()
        .all()
    )
    missing = set(payload.permission_codes) - {p.code for p in perms}
    if missing:
        raise NotFoundError(f"Unknown permission codes: {', '.join(sorted(missing))}")

    role.permissions = perms
    db.commit()
    db.refresh(role)
    return role


@router.delete("/{role_id}", response_model=MessageResponse, summary="Delete a custom role")
def delete_role(
    role_id: int,
    _: User = Depends(RequirePermissions("role:manage")),
    db: Session = Depends(get_db),
):
    role = db.get(Role, role_id)
    if role is None:
        raise NotFoundError("Role not found.")
    if role.is_system_role:
        raise BusinessRuleError("System roles cannot be deleted.")

    in_use = db.execute(select(User).where(User.role_id == role.id)).scalars().first()
    if in_use:
        raise BusinessRuleError("This role is still assigned to one or more users.")

    db.delete(role)
    db.commit()
    return MessageResponse(message=f"Role '{role.name}' deleted.")
