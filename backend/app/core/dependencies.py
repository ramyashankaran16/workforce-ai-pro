"""FastAPI dependencies: current user, role guards and permission guards."""

from typing import List, Optional, Set

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import (
    AccountLockedError,
    AuthenticationError,
    PermissionDeniedError,
)
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.models.employee import Employee
from app.models.enums import UserStatus
from app.models.user import User
from app.utils.date_utils import utcnow

bearer_scheme = HTTPBearer(auto_error=False)

# Declared so Swagger renders the Authorize button; the token itself is read
# from the Authorization header by bearer_scheme.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/token", auto_error=False
)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    _oauth: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the caller from a bearer access token."""
    token = credentials.credentials if credentials else _oauth
    if not token:
        raise AuthenticationError("Not authenticated.")

    payload = decode_token(token, expected_type=ACCESS_TOKEN_TYPE)
    if not payload:
        raise AuthenticationError("Invalid or expired token.")

    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise AuthenticationError("Malformed token subject.")

    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise AuthenticationError("User no longer exists.")

    if user.status != UserStatus.ACTIVE:
        raise AuthenticationError(f"Account is {user.status.value}.")

    if user.locked_until and user.locked_until > utcnow():
        raise AccountLockedError("Account is temporarily locked.")

    return user


def get_current_employee(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Employee:
    """The employee profile linked to the caller. 403 if none is linked."""
    employee = (
        db.query(Employee)
        .filter(Employee.user_id == current_user.id, Employee.is_deleted.is_(False))
        .first()
    )
    if employee is None:
        raise PermissionDeniedError("No employee profile is linked to this account.")
    return employee


def user_permission_codes(user: User) -> Set[str]:
    if not user.role:
        return set()
    return {p.code for p in user.role.permissions}


class RequirePermissions:
    """
    Dependency factory guarding an endpoint by permission code.

        @router.post("", dependencies=[Depends(RequirePermissions("employee:create"))])

    require_all=False lets any one of the listed codes pass.
    """

    def __init__(self, *codes: str, require_all: bool = True) -> None:
        self.codes = set(codes)
        self.require_all = require_all

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        held = user_permission_codes(current_user)
        ok = self.codes.issubset(held) if self.require_all else bool(self.codes & held)
        if not ok:
            missing = ", ".join(sorted(self.codes - held))
            raise PermissionDeniedError(f"Missing permission: {missing}")
        return current_user


class RequireRoles:
    """Guard by role name, e.g. RequireRoles("admin", "hr")."""

    def __init__(self, *roles: str) -> None:
        self.roles = {r.lower() for r in roles}

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if (current_user.role_name or "").lower() not in self.roles:
            allowed = ", ".join(sorted(self.roles))
            raise PermissionDeniedError(f"This action is restricted to: {allowed}")
        return current_user


def require_min_level(level: int):
    """
    Guard by hierarchy level (admin=1 ... employee=4).
    require_min_level(2) allows admin and hr.
    """

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.role or current_user.role.hierarchy_level > level:
            raise PermissionDeniedError("Insufficient authority for this action.")
        return current_user

    return dependency


# Common shorthands
require_admin = RequireRoles("admin")
require_hr = RequireRoles("admin", "hr")
require_manager = RequireRoles("admin", "hr", "manager")


def can_access_employee(user: User, employee: Employee, db: Session) -> bool:
    """
    Row-level check used by employee-scoped endpoints.

    admin/hr see everyone, managers see their own reportees, employees see
    only themselves.
    """
    role = (user.role_name or "").lower()
    if role in {"admin", "hr"}:
        return True
    if employee.user_id == user.id:
        return True
    if role == "manager":
        manager_profile = (
            db.query(Employee).filter(Employee.user_id == user.id).first()
        )
        if manager_profile and employee.manager_id == manager_profile.id:
            return True
    return False

