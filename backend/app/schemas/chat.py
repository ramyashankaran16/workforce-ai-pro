"""Chat schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import MessageType
from app.schemas.common import ORMBase


class ConversationStart(BaseModel):
    user_id: int = Field(..., description="The other participant")


class ConversationRead(BaseModel):
    id: int
    partner_id: int
    partner_name: str
    partner_avatar: Optional[str] = None
    last_message_preview: Optional[str] = None
    last_message_at: Optional[datetime] = None
    unread_count: int = 0
    is_archived: bool = False


class MessageSend(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    message_type: MessageType = MessageType.TEXT


class MessageEdit(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class MessageRead(ORMBase):
    id: int
    conversation_id: int
    sender_id: int
    content: str
    message_type: MessageType
    attachment_path: Optional[str] = None
    attachment_name: Optional[str] = None
    is_read: bool
    read_at: Optional[datetime] = None
    is_edited: bool
    is_deleted: bool
    created_at: datetime
