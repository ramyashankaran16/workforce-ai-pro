"""Authentication business logic: login, refresh, logout, password changes."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    AccountLockedError,
    AuthenticationError,
    BusinessRuleError,
    DuplicateError,
    NotFoundError,
)
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_temp_password,
    hash_password,
    refresh_token_expiry,
    verify_password,
)
from app.models.audit import LoginHistory
from app.models.employee import Employee
from app.models.enums import UserStatus
from app.models.role import Role
from app.models.user import RefreshToken, User
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _record_login(
    db: Session,
    email: str,
    success: bool,
    user_id: Optional[int] = None,
    reason: Optional[str] = None,
    ip: Optional[str] = None,
    agent: Optional[str] = None,
) -> None:
    db.add(
        LoginHistory(
            user_id=user_id,
            email_attempted=email,
            is_successful=success,
            failure_reason=reason,
            ip_address=ip,
            user_agent=(agent or "")[:300] or None,
        )
    )


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.execute(
        select(User).where(User.email == email.lower(), User.is_deleted.is_(False))
    ).scalar_one_or_none()


def permission_codes_for(user: User) -> List[str]:
    if not user.role:
        return []
    return sorted(p.code for p in user.role.permissions)


def authenticate(
    db: Session,
    email: str,
    password: str,
    ip: Optional[str] = None,
    agent: Optional[str] = None,
) -> User:
    """
    Verify credentials, applying lockout after repeated failures.

    The same generic message is returned for unknown email and wrong password
    so the endpoint cannot be used to enumerate accounts.
    """
    email = email.lower().strip()
    user = get_user_by_email(db, email)

    if user is None:
        _record_login(db, email, False, reason="unknown_email", ip=ip, agent=agent)
        db.commit()
        raise AuthenticationError("Incorrect email or password.")

    if user.locked_until and user.locked_until > utcnow():
        remaining = int((user.locked_until - utcnow()).total_seconds() // 60) + 1
        _record_login(db, email, False, user.id, "locked", ip, agent)
        db.commit()
        raise AccountLockedError(f"Account locked. Try again in {remaining} minute(s).")

    if not verify_password(password, user.hashed_password):
        user.failed_login_attempts += 1
        reason = "bad_password"
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
            reason = "locked_out"
        _record_login(db, email, False, user.id, reason, ip, agent)
        db.commit()
        if reason == "locked_out":
            raise AccountLockedError(
                f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} minutes."
            )
        raise AuthenticationError("Incorrect email or password.")

    if user.status != UserStatus.ACTIVE:
        _record_login(db, email, False, user.id, f"status_{user.status.value}", ip, agent)
        db.commit()
        raise AuthenticationError(f"Account is {user.status.value}.")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    user.last_login_ip = ip
    _record_login(db, email, True, user.id, None, ip, agent)
    db.commit()
    db.refresh(user)
    return user


def issue_tokens(
    db: Session, user: User, ip: Optional[str] = None, agent: Optional[str] = None
) -> Tuple[str, str, int]:
    """Create an access token and persist a refresh token so it can be revoked."""
    access = create_access_token(
        str(user.id),
        extra_claims={"email": user.email, "role": user.role_name},
    )
    refresh = create_refresh_token(str(user.id))

    db.add(
        RefreshToken(
            user_id=user.id,
            token=refresh,
            expires_at=refresh_token_expiry().replace(tzinfo=None),
            ip_address=ip,
            user_agent=(agent or "")[:300] or None,
        )
    )
    db.commit()
    return access, refresh, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def refresh_access_token(db: Session, refresh_token: str) -> Tuple[str, int]:
    payload = decode_token(refresh_token, expected_type=REFRESH_TOKEN_TYPE)
    if not payload:
        raise AuthenticationError("Invalid or expired refresh token.")

    stored = db.execute(
        select(RefreshToken).where(RefreshToken.token == refresh_token)
    ).scalar_one_or_none()

    if stored is None or stored.is_revoked:
        raise AuthenticationError("Refresh token has been revoked.")
    if stored.expires_at < utcnow():
        raise AuthenticationError("Refresh token has expired.")

    user = db.get(User, stored.user_id)
    if user is None or user.is_deleted or user.status != UserStatus.ACTIVE:
        raise AuthenticationError("User is no longer active.")

    access = create_access_token(
        str(user.id), extra_claims={"email": user.email, "role": user.role_name}
    )
    return access, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def revoke_refresh_token(db: Session, refresh_token: str) -> None:
    stored = db.execute(
        select(RefreshToken).where(RefreshToken.token == refresh_token)
    ).scalar_one_or_none()
    if stored and not stored.is_revoked:
        stored.is_revoked = True
        stored.revoked_at = utcnow()
        db.commit()


def revoke_all_tokens(db: Session, user_id: int) -> int:
    tokens = (
        db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.is_revoked.is_(False)
            )
        )
        .scalars()
        .all()
    )
    for token in tokens:
        token.is_revoked = True
        token.revoked_at = utcnow()
    db.commit()
    return len(tokens)


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.hashed_password):
        raise AuthenticationError("Current password is incorrect.")
    if verify_password(new, user.hashed_password):
        raise BusinessRuleError("The new password must differ from the current one.")

    user.hashed_password = hash_password(new)
    user.must_change_password = False
    db.commit()
    revoke_all_tokens(db, user.id)


def reset_password(db: Session, user_id: int, new_password: Optional[str]) -> str:
    """Admin/HR reset. Returns the password so it can be handed to the user."""
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise NotFoundError("User not found.")

    password = new_password or generate_temp_password()
    user.hashed_password = hash_password(password)
    user.must_change_password = True
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    revoke_all_tokens(db, user.id)
    return password


def create_user(
    db: Session,
    email: str,
    full_name: str,
    role_name: str,
    password: Optional[str] = None,
    phone: Optional[str] = None,
    username: Optional[str] = None,
) -> Tuple[User, Optional[str]]:
    """Create an account. Returns the user and the temp password if generated."""
    email = email.lower().strip()
    if get_user_by_email(db, email):
        raise DuplicateError(f"A user with email {email} already exists.")

    if username:
        existing = db.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()
        if existing:
            raise DuplicateError(f"Username '{username}' is taken.")

    role = db.execute(
        select(Role).where(Role.name == role_name.lower())
    ).scalar_one_or_none()
    if role is None:
        raise NotFoundError(f"Role '{role_name}' does not exist.")

    generated = password is None
    final_password = password or generate_temp_password()

    user = User(
        email=email,
        username=username,
        full_name=full_name.strip(),
        phone=phone,
        hashed_password=hash_password(final_password),
        role_id=role.id,
        status=UserStatus.ACTIVE,
        must_change_password=generated,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, (final_password if generated else None)


def build_profile_payload(db: Session, user: User) -> dict:
    """Assemble the /auth/me payload, including permissions and employee link."""
    employee = (
        db.execute(select(Employee).where(Employee.user_id == user.id))
        .scalars()
        .first()
    )
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "phone": user.phone,
        "avatar_url": user.avatar_url,
        "status": user.status,
        "is_email_verified": user.is_email_verified,
        "must_change_password": user.must_change_password,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "role": user.role,
        "permissions": permission_codes_for(user),
        "employee_id": employee.id if employee else None,
        "employee_code": employee.employee_code if employee else None,
    }
