"""Password hashing (bcrypt directly) and JWT creation / verification."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

# bcrypt silently truncates anything past 72 bytes, so reject it up front
BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    """Hash a plaintext password. bcrypt is used directly, without passlib."""
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > BCRYPT_MAX_BYTES:
        raise ValueError("Password must be 72 bytes or fewer.")
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Constant-time comparison. Returns False on malformed hashes."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def _create_token(
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": secrets.token_urlsafe(16),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(
    subject: str, extra_claims: Optional[Dict[str, Any]] = None
) -> str:
    return _create_token(
        subject,
        ACCESS_TOKEN_TYPE,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims,
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(
        subject,
        REFRESH_TOKEN_TYPE,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return the payload, or None if the token is invalid, expired or the wrong type."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None

    if expected_type and payload.get("type") != expected_type:
        return None
    return payload


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


def generate_temp_password(length: int = 12) -> str:
    """Readable temporary password for admin-created accounts."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    core = "".join(secrets.choice(alphabet) for _ in range(length - 2))
    return f"{core}@{secrets.choice('123456789')}"
