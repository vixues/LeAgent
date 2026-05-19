"""WebSocket connection manager — in-memory only (no Redis fan-out)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class DistributedConnectionManager:
    """In-memory WebSocket connection manager (no Redis pub/sub)."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._local: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(session_id, []).append(websocket)
        self._local.setdefault(session_id, []).append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        for store in (self._connections, self._local):
            conns = store.get(session_id, [])
            if websocket in conns:
                conns.remove(websocket)
            if not conns:
                store.pop(session_id, None)

    async def broadcast(self, session_id: str, message: Any) -> None:
        for ws in list(self._connections.get(session_id, [])):
            try:
                if isinstance(message, str):
                    await ws.send_text(message)
                elif isinstance(message, dict):
                    await ws.send_json(message)
                else:
                    await ws.send_text(str(message))
            except Exception:
                self.disconnect(session_id, ws)

    def attach_redis(self, _redis_client: Any) -> None:
        pass

    async def aclose(self) -> None:
        for session_id, conns in list(self._connections.items()):
            for ws in conns:
                try:
                    await ws.close()
                except Exception:
                    pass
        self._connections.clear()
        self._local.clear()
