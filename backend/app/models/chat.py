"""One-to-one chat: conversations, participants and messages."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import MessageType, enum_col
from app.models.mixins import TimestampMixin


class Conversation(Base, TimestampMixin):
    """
    A private thread between exactly two users.

    user_one_id is always the smaller user id, which makes the unique
    constraint enough to prevent duplicate threads.
    """

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("user_one_id", "user_two_id", name="uq_conversation_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_one_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_two_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    last_message_preview: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user_one: Mapped["User"] = relationship(foreign_keys=[user_one_id])
    user_two: Mapped["User"] = relationship(foreign_keys=[user_two_id])
    messages: Mapped[List["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.user_one_id}<->{self.user_two_id}>"


class Message(Base, TimestampMixin):
    """A single chat message."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[MessageType] = mapped_column(
        enum_col(MessageType), default=MessageType.TEXT, nullable=False
    )
    attachment_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    attachment_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attachment_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    sender: Mapped["User"] = relationship(foreign_keys=[sender_id])

    def __repr__(self) -> str:
        return f"<Message conv={self.conversation_id} from={self.sender_id}>"
