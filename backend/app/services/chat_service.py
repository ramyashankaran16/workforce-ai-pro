"""
One-to-one chat: conversation resolution, message persistence, unread counts.

A conversation is identified by its ordered pair of user ids -- the smaller id
is always `user_one_id`. That normalisation is what makes the unique constraint
work: without it, A-to-B and B-to-A would create two separate threads.
"""

import logging
import os
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.models.chat import Conversation, Message
from app.models.enums import MessageType, NotificationCategory, NotificationType
from app.models.user import User
from app.services import notification_service
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)

PREVIEW_LENGTH = 120


def _ordered(a: int, b: int) -> Tuple[int, int]:
    return (a, b) if a < b else (b, a)


def get_or_create(db: Session, user_id: int, other_user_id: int) -> Conversation:
    if user_id == other_user_id:
        raise BusinessRuleError("You cannot start a conversation with yourself.")

    other = db.get(User, other_user_id)
    if other is None or other.is_deleted:
        raise NotFoundError("That user does not exist.")

    one, two = _ordered(user_id, other_user_id)
    conversation = db.execute(
        select(Conversation).where(
            Conversation.user_one_id == one, Conversation.user_two_id == two
        )
    ).scalar_one_or_none()

    if conversation is None:
        conversation = Conversation(user_one_id=one, user_two_id=two)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
    return conversation


def assert_participant(conversation: Conversation, user_id: int) -> None:
    if user_id not in {conversation.user_one_id, conversation.user_two_id}:
        raise PermissionDeniedError("You are not part of this conversation.")


def other_party(conversation: Conversation, user_id: int) -> int:
    return (
        conversation.user_two_id
        if conversation.user_one_id == user_id
        else conversation.user_one_id
    )


def send_message(
    db: Session,
    conversation_id: int,
    sender_id: int,
    content: str,
    message_type: MessageType = MessageType.TEXT,
    attachment_path: Optional[str] = None,
    attachment_name: Optional[str] = None,
    attachment_size: Optional[int] = None,
) -> Message:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found.")
    assert_participant(conversation, sender_id)

    message = Message(
        conversation_id=conversation.id,
        sender_id=sender_id,
        content=content,
        message_type=message_type,
        attachment_path=attachment_path,
        attachment_name=attachment_name,
        attachment_size=attachment_size,
    )
    db.add(message)

    conversation.last_message_preview = content[:PREVIEW_LENGTH]
    conversation.last_message_at = utcnow()
    conversation.is_archived = False

    db.flush()

    recipient_id = other_party(conversation, sender_id)
    sender = db.get(User, sender_id)
    notification_service.notify(
        db,
        recipient_id,
        title=f"Message from {sender.full_name if sender else 'a colleague'}",
        message=content[:PREVIEW_LENGTH],
        category=NotificationCategory.CHAT,
        notification_type=NotificationType.INFO,
        reference_type="conversation",
        reference_id=conversation.id,
        action_url=f"/chat/{conversation.id}",
        commit=False,
    )

    db.commit()
    db.refresh(message)
    return message


def list_conversations(db: Session, user_id: int) -> List[dict]:
    conversations = (
        db.execute(
            select(Conversation)
            .where(
                or_(
                    Conversation.user_one_id == user_id,
                    Conversation.user_two_id == user_id,
                )
            )
            .order_by(Conversation.last_message_at.desc().nullslast())
        )
        .scalars()
        .all()
    )

    out = []
    for conversation in conversations:
        partner_id = other_party(conversation, user_id)
        partner = db.get(User, partner_id)
        unread = db.execute(
            select(func.count(Message.id)).where(
                Message.conversation_id == conversation.id,
                Message.sender_id != user_id,
                Message.is_read.is_(False),
                Message.is_deleted.is_(False),
            )
        ).scalar() or 0

        out.append(
            {
                "id": conversation.id,
                "partner_id": partner_id,
                "partner_name": partner.full_name if partner else "Unknown",
                "partner_avatar": partner.avatar_url if partner else None,
                "last_message_preview": conversation.last_message_preview,
                "last_message_at": conversation.last_message_at,
                "unread_count": int(unread),
                "is_archived": conversation.is_archived,
            }
        )
    return out


def mark_conversation_read(db: Session, conversation_id: int, user_id: int) -> int:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found.")
    assert_participant(conversation, user_id)

    unread = (
        db.execute(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.sender_id != user_id,
                Message.is_read.is_(False),
            )
        )
        .scalars()
        .all()
    )
    for message in unread:
        message.is_read = True
        message.read_at = utcnow()
    db.commit()
    return len(unread)


def edit_message(db: Session, message_id: int, user_id: int, content: str) -> Message:
    message = db.get(Message, message_id)
    if message is None or message.is_deleted:
        raise NotFoundError("Message not found.")
    if message.sender_id != user_id:
        raise PermissionDeniedError("You can only edit your own messages.")

    message.content = content
    message.is_edited = True
    message.edited_at = utcnow()

    conversation = db.get(Conversation, message.conversation_id)
    latest = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.id.desc())
    ).scalars().first()
    if latest and latest.id == message.id:
        conversation.last_message_preview = content[:PREVIEW_LENGTH]

    db.commit()
    db.refresh(message)
    return message


def delete_message(db: Session, message_id: int, user_id: int) -> None:
    """Soft delete, so the thread keeps its shape for the other party."""
    message = db.get(Message, message_id)
    if message is None or message.is_deleted:
        raise NotFoundError("Message not found.")
    if message.sender_id != user_id:
        raise PermissionDeniedError("You can only delete your own messages.")

    message.is_deleted = True
    message.content = "[message deleted]"
    db.commit()


def total_unread(db: Session, user_id: int) -> int:
    conversation_ids = (
        db.execute(
            select(Conversation.id).where(
                or_(
                    Conversation.user_one_id == user_id,
                    Conversation.user_two_id == user_id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not conversation_ids:
        return 0
    return int(
        db.execute(
            select(func.count(Message.id)).where(
                Message.conversation_id.in_(conversation_ids),
                Message.sender_id != user_id,
                Message.is_read.is_(False),
                Message.is_deleted.is_(False),
            )
        ).scalar()
        or 0
    )


def db_conversation(db: Session, conversation_id: int) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found.")
    return conversation
