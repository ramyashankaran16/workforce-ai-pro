"""RBAC: roles, permissions and their association."""

from typing import List, Optional

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

# Many-to-many join between roles and permissions
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        Integer,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Role(Base, TimestampMixin):
    """A named role such as admin, hr, manager or employee."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Lower level = more authority (admin=1, hr=2, manager=3, employee=4).
    # Used for "can this user act on that user" checks.
    hierarchy_level: Mapped[int] = mapped_column(Integer, default=99, nullable=False)

    is_system_role: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    permissions: Mapped[List["Permission"]] = relationship(
        secondary=role_permissions, back_populates="roles", lazy="selectin"
    )
    users: Mapped[List["User"]] = relationship(back_populates="role")

    def __repr__(self) -> str:
        return f"<Role {self.name}>"


class Permission(Base, TimestampMixin):
    """A single granular capability, e.g. employee:create."""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    module: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    roles: Mapped[List["Role"]] = relationship(
        secondary=role_permissions, back_populates="permissions"
    )

    def __repr__(self) -> str:
        return f"<Permission {self.code}>"
