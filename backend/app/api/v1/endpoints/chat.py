"""One-to-one chat endpoints."""

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.pagination import Page, PaginationParams, paginate
from app.models.chat import Conversation, Message
from app.models.user import User
from app.schemas.chat import (
    ConversationRead,
    ConversationStart,
    MessageEdit,
    MessageRead,
    MessageSend,
)
from app.schemas.common import MessageResponse
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.get(
    "/conversations",
    response_model=List[ConversationRead],
    summary="Own threads with unread counts",
)
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.list_conversations(db, current_user.id)


@router.get("/unread", response_model=MessageResponse, summary="Total unread messages")
def unread(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total = chat_service.total_unread(db, current_user.id)
    return MessageResponse(message=f"{total} unread message(s).", data={"unread": total})


@router.post(
    "/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start or fetch a thread",
)
def start_conversation(
    payload: ConversationStart,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Idempotent. The pair is normalised so A-to-B and B-to-A resolve to the same
    thread rather than creating two.
    """
    conversation = chat_service.get_or_create(db, current_user.id, payload.user_id)
    partner = db.get(User, chat_service.other_party(conversation, current_user.id))
    return {
        "id": conversation.id,
        "partner_id": partner.id,
        "partner_name": partner.full_name,
        "partner_avatar": partner.avatar_url,
        "last_message_preview": conversation.last_message_preview,
        "last_message_at": conversation.last_message_at,
        "unread_count": 0,
        "is_archived": conversation.is_archived,
    }


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=Page[MessageRead],
    summary="Message history",
)
def list_messages(
    conversation_id: int,
    params: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Conversation not found.")
    chat_service.assert_participant(conversation, current_user.id)

    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
    )
    rows, total = paginate(db, stmt, params)
    return Page[MessageRead].create(
        [MessageRead.model_validate(r) for r in rows], total, params
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message",
)
def send_message(
    conversation_id: int,
    payload: MessageSend,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """REST path. The WebSocket route delivers the same message live."""
    return chat_service.send_message(
        db,
        conversation_id,
        current_user.id,
        payload.content,
        payload.message_type,
    )


@router.post(
    "/conversations/{conversation_id}/read",
    response_model=MessageResponse,
    summary="Mark a thread read",
)
def mark_read(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = chat_service.mark_conversation_read(db, conversation_id, current_user.id)
    return MessageResponse(message=f"Marked {count} message(s) as read.")


@router.patch(
    "/messages/{message_id}", response_model=MessageRead, summary="Edit own message"
)
def edit_message(
    message_id: int,
    payload: MessageEdit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.edit_message(
        db, message_id, current_user.id, payload.content
    )


@router.delete(
    "/messages/{message_id}",
    response_model=MessageResponse,
    summary="Delete own message",
)
def delete_message(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft delete, so the thread keeps its shape for the other participant."""
    chat_service.delete_message(db, message_id, current_user.id)
    return MessageResponse(message="Message deleted.")
