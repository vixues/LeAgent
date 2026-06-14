"""Progress reporting primitives.

The runner records a :class:`NodeProgressState` per node; nodes can call
``update(value, max, preview)`` inside their execute. Every state change
is forwarded to all registered :class:`ProgressHandler` instances so the
server can publish WebSocket events.
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    BLOCKED = "blocked"
    CACHED = "cached"
    SKIPPED = "skipped"


@dataclass
class NodeProgressState:
    node_id: str
    status: NodeStatus = NodeStatus.PENDING
    value: float = 0.0
    max: float = 1.0
    preview: Any = None
    message: str = ""
    started_at_ms: int | None = None
    finished_at_ms: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


ProgressHandler = Callable[["ProgressEvent"], None | Awaitable[None]]


@dataclass
class ProgressEvent:
    type: str  # one of: execution_start, executing, progress, executed, etc.
    prompt_id: str
    node_id: str | None = None
    state: NodeProgressState | None = None
    data: dict[str, Any] = field(default_factory=dict)


_current_node: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_node", default=None)


class CurrentNodeContext:
    """Context manager that scopes ``current_node`` for ``progress.update``
    calls made from a node's execute coroutine.
    """

    def __init__(self, node_id: str) -> None:
        self._node_id = node_id
        self._token: contextvars.Token[str | None] | None = None

    def __enter__(self) -> "CurrentNodeContext":
        self._token = _current_node.set(self._node_id)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._token is not None:
            _current_node.reset(self._token)


class ProgressRegistry:
    """Per-prompt progress store shared by the runner and handlers."""

    def __init__(self, prompt_id: str) -> None:
        self.prompt_id = prompt_id
        self._states: dict[str, NodeProgressState] = {}
        self._handlers: list[ProgressHandler] = []
        self._lock = threading.RLock()

    def add_handler(self, handler: ProgressHandler) -> None:
        with self._lock:
            self._handlers.append(handler)

    def remove_handler(self, handler: ProgressHandler) -> None:
        with self._lock:
            try:
                self._handlers.remove(handler)
            except ValueError:
                pass

    def state(self, node_id: str) -> NodeProgressState:
        with self._lock:
            st = self._states.get(node_id)
            if st is None:
                st = NodeProgressState(node_id=node_id)
                self._states[node_id] = st
            return st

    def emit(self, event: ProgressEvent) -> None:
        with self._lock:
            handlers = list(self._handlers)
        for h in handlers:
            try:
                result = h(event)
                if inspect.iscoroutine(result):
                    try:
                        asyncio.get_running_loop().create_task(result)
                    except RuntimeError:
                        result.close()
            except Exception:  # noqa: BLE001
                continue

    def update(
        self,
        *,
        value: float | None = None,
        max: float | None = None,
        preview: Any | None = None,
        message: str | None = None,
        node_id: str | None = None,
    ) -> None:
        nid = node_id or _current_node.get()
        if nid is None:
            return
        st = self.state(nid)
        if value is not None:
            st.value = value
        if max is not None:
            st.max = max
        if preview is not None:
            st.preview = preview
        if message is not None:
            st.message = message
        self.emit(ProgressEvent(type="progress", prompt_id=self.prompt_id, node_id=nid, state=st))

    def set_status(
        self,
        node_id: str,
        status: NodeStatus,
        *,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        st = self.state(node_id)
        st.status = status
        if error is not None:
            st.error = error
        if metadata is not None:
            st.metadata.update(metadata)
        self.emit(ProgressEvent(
            type="executing" if status == NodeStatus.RUNNING else f"node_{status.value}",
            prompt_id=self.prompt_id,
            node_id=node_id,
            state=st,
        ))
