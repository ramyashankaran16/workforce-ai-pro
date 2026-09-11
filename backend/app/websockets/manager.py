"""
WebSocket connection registry.

KNOWN LIMITATION: this state lives in the process. Run `uvicorn --workers 4`
and a socket held by worker 2 is unreachable from worker 3, so a message
published there is silently lost. Scaling horizontally requires Redis pub/sub,
with each worker subscribing and fanning out to its own local sockets.

The application is therefore designed to run single-worker. That is a real
constraint, not an oversight.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """user_id -> the set of sockets that user currently has open."""

    def __init__(self) -> None:
        self._connections: Dict[int, Set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[user_id].add(websocket)
        logger.info(
            "User %s connected (%d socket(s))", user_id, len(self._connections[user_id])
        )

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: int, payload: Dict[str, Any]) -> int:
        """
        Deliver to every socket that user has open.

        One person with three tabs has three sockets; all three should update,
        which is why the value is a set rather than a single connection.
        """
        sockets = list(self._connections.get(user_id, set()))
        delivered = 0
        dead = []

        for socket in sockets:
            try:
                await socket.send_json(payload)
                delivered += 1
            except Exception:
                dead.append(socket)

        for socket in dead:
            await self.disconnect(user_id, socket)
        return delivered

    async def broadcast(self, payload: Dict[str, Any]) -> int:
        total = 0
        for user_id in list(self._connections.keys()):
            total += await self.send_to_user(user_id, payload)
        return total

    def is_online(self, user_id: int) -> bool:
        return bool(self._connections.get(user_id))

    def online_users(self) -> Set[int]:
        return set(self._connections.keys())

    def connection_count(self) -> int:
        return sum(len(sockets) for sockets in self._connections.values())


manager = ConnectionManager()
