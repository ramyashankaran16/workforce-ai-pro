"""
WebSocket routes for chat and live monitoring.

The token is passed as a query parameter because browsers cannot set headers on
a WebSocket handshake. That puts it in the URL, where it may reach server logs;
the mitigations are short access-token lifetimes and not logging query strings
in production.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.models.enums import MessageType, UserStatus
from app.models.user import User
from app.services import chat_service
from app.websockets.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSockets"])


def _authenticate(token: str, db: Session) -> Optional[User]:
    payload = decode_token(token, expected_type=ACCESS_TOKEN_TYPE)
    if not payload:
        return None
    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        return None

    user = db.get(User, user_id)
    if user is None or user.is_deleted or user.status != UserStatus.ACTIVE:
        return None
    return user


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket, token: str = Query(...)):
    db = SessionLocal()
    user = _authenticate(token, db)
    if user is None:
        await websocket.close(code=4401)  # unauthorised
        db.close()
        return

    await manager.connect(user.id, websocket)
    try:
        await websocket.send_json(
            {"type": "connected", "user_id": user.id, "online": True}
        )

        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if action == "send":
                conversation_id = data.get("conversation_id")
                content = (data.get("content") or "").strip()
                if not conversation_id or not content:
                    await websocket.send_json(
                        {"type": "error", "message": "conversation_id and content are required."}
                    )
                    continue

                try:
                    message = chat_service.send_message(
                        db, conversation_id, user.id, content, MessageType.TEXT
                    )
                except Exception as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
                    continue

                payload = {
                    "type": "message",
                    "id": message.id,
                    "conversation_id": message.conversation_id,
                    "sender_id": message.sender_id,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                }
                await websocket.send_json({**payload, "own": True})

                conversation = chat_service.db_conversation(db, conversation_id)
                recipient_id = chat_service.other_party(conversation, user.id)
                await manager.send_to_user(recipient_id, payload)
                continue

            await websocket.send_json(
                {"type": "error", "message": f"Unknown action '{action}'."}
            )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Chat socket error for user %s", user.id)
    finally:
        await manager.disconnect(user.id, websocket)
        db.close()


@router.websocket("/ws/monitoring")
async def monitoring_socket(websocket: WebSocket, token: str = Query(...)):
    """
    Live channel for events that genuinely need to arrive within seconds --
    critical risk alerts, mainly. Aggregate dashboard numbers stay on the
    polling endpoint, because headcount does not change second to second.
    """
    db = SessionLocal()
    user = _authenticate(token, db)
    if user is None:
        await websocket.close(code=4401)
        db.close()
        return

    if (user.role_name or "").lower() not in {"admin", "hr", "manager"}:
        await websocket.close(code=4403)  # forbidden
        db.close()
        return

    await manager.connect(user.id, websocket)
    try:
        from app.services import analytics_service

        await websocket.send_json(
            {"type": "snapshot", "data": analytics_service.live_snapshot(db)}
        )
        while True:
            data = await websocket.receive_json()
            if data.get("action") == "refresh":
                await websocket.send_json(
                    {"type": "snapshot", "data": analytics_service.live_snapshot(db)}
                )
            else:
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Monitoring socket error for user %s", user.id)
    finally:
        await manager.disconnect(user.id, websocket)
        db.close()
