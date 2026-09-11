"""Authentication accounts and refresh tokens."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import UserStatus, enum_col
from app.models.mixins import SoftDeleteMixin, TimestampMixin


class User(Base, TimestampMixin, SoftDeleteMixin):
    """Login identity. The HR profile lives on the linked Employee row."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(80), unique=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[UserStatus] = mapped_column(
        enum_col(UserStatus), default=UserStatus.ACTIVE, nullable=False, index=True
    )

    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # ---- relationships
    role: Mapped["Role"] = relationship(back_populates="users", lazy="joined")
    employee: Mapped[Optional["Employee"]] = relationship(
        back_populates="user", uselist=False
    )
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[List["Notification"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(back_populates="user")

    @property
    def role_name(self) -> Optional[str]:
        return self.role.name if self.role else None

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class RefreshToken(Base, TimestampMixin):
    """Persisted refresh tokens so sessions can be revoked server-side."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    def __repr__(self) -> str:
        return f"<RefreshToken user={self.user_id} revoked={self.is_revoked}>"
