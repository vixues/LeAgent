"""Session control registry: steer + queue for running agent turns.

Codex-style mid-turn interaction:

* **Steer** — inject a user message into the *current* running turn. The
  query loop drains steer messages at every tool-batch boundary and
  appends them as new user messages (history is append-only; no
  rewriting of already-sent context).
* **Queue** — park messages to dispatch as the *next* turn once the
  current one finishes. The backend stores them; the frontend pops and
  dispatches through the normal ``/chat/stream`` path when the stream
  ends.

Single-worker in-process semantics, same constraint envelope as
``ExecutionRunRegistry``.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class QueuedMessage:
    """A message queued for dispatch after the current turn."""

    id: str
    content: str
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "content": self.content, "created_at": self.created_at}


class SessionControlRegistry:
    """Per-session steer queues + next-turn message queues."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._steer: dict[str, deque[str]] = {}
        self._queued: dict[str, list[QueuedMessage]] = {}
        self._plan_mode: set[str] = set()

    # -- plan mode ----------------------------------------------------------

    def set_plan_mode(self, session_id: str, active: bool) -> None:
        """Durable per-session plan-mode flag (survives per-call context copies)."""
        with self._lock:
            if active:
                self._plan_mode.add(str(session_id))
            else:
                self._plan_mode.discard(str(session_id))
        logger.info("plan_mode_set", session_id=str(session_id), active=active)

    def plan_mode_active(self, session_id: str | None) -> bool:
        if session_id is None:
            return False
        with self._lock:
            return str(session_id) in self._plan_mode

    # -- steer ------------------------------------------------------------

    def push_steer(self, session_id: str, content: str) -> None:
        content = (content or "").strip()
        if not content:
            raise ValueError("steer content must be non-empty")
        with self._lock:
            self._steer.setdefault(str(session_id), deque()).append(content)
        logger.info("steer_pushed", session_id=str(session_id), preview=content[:80])

    def drain_steer(self, session_id: str | None) -> list[str]:
        """Pop all pending steer messages for the session (FIFO)."""
        if session_id is None:
            return []
        with self._lock:
            dq = self._steer.get(str(session_id))
            if not dq:
                return []
            out = list(dq)
            dq.clear()
        return out

    def has_steer(self, session_id: str | None) -> bool:
        if session_id is None:
            return False
        with self._lock:
            return bool(self._steer.get(str(session_id)))

    # -- queue ------------------------------------------------------------

    def queue_message(self, session_id: str, content: str) -> QueuedMessage:
        content = (content or "").strip()
        if not content:
            raise ValueError("queued content must be non-empty")
        msg = QueuedMessage(id=uuid.uuid4().hex[:12], content=content)
        with self._lock:
            self._queued.setdefault(str(session_id), []).append(msg)
        return msg

    def list_queued(self, session_id: str) -> list[QueuedMessage]:
        with self._lock:
            return list(self._queued.get(str(session_id), ()))

    def remove_queued(self, session_id: str, message_id: str) -> bool:
        with self._lock:
            items = self._queued.get(str(session_id))
            if not items:
                return False
            for i, m in enumerate(items):
                if m.id == message_id:
                    items.pop(i)
                    return True
        return False

    def pop_next_queued(self, session_id: str) -> QueuedMessage | None:
        with self._lock:
            items = self._queued.get(str(session_id))
            if not items:
                return None
            return items.pop(0)

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._steer.pop(str(session_id), None)
            self._queued.pop(str(session_id), None)
            self._plan_mode.discard(str(session_id))


_REGISTRY: SessionControlRegistry | None = None


def get_session_control_registry() -> SessionControlRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = SessionControlRegistry()
    return _REGISTRY


def reset_session_control_registry() -> None:
    """Testing hook."""
    global _REGISTRY
    _REGISTRY = None
