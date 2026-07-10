"""Live tool-output bus: incremental stdout/stderr streaming per session.

The :class:`ToolOutputBus` is the single in-process fan-out point for
subprocess output produced by :class:`ExecutionEngine`. Producers publish
``(session_id, tool_call_id, stream, chunk)`` records as the process
writes them; consumers (the chat terminal SSE endpoint) subscribe to a
session and receive ``tool_output_delta`` frames in real time.

Design notes:

* **Single-worker semantics** — in-memory queues, consistent with
  ``ExecutionRunRegistry`` / ``SessionControlRegistry``.
* **Bounded backlog** — the bus keeps the tail of each call's output
  (``_BACKLOG_LIMIT`` bytes per call, ``_MAX_CALLS`` calls per session)
  so late subscribers and the full-output endpoint
  (``GET /chat/sessions/{id}/tool-output/{call_id}``) can recover
  output that the LLM-facing ``tool_result`` truncated.
* **Never blocks the producer** — slow subscribers drop frames
  (queue full) rather than stalling the subprocess reader.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal

import structlog

logger = structlog.get_logger(__name__)

#: Max bytes of backlog retained per tool call (tail).
_BACKLOG_LIMIT = 2 * 1024 * 1024
#: Max distinct calls tracked per session (LRU).
_MAX_CALLS = 64
#: Per-subscriber queue capacity (frames).
_QUEUE_CAPACITY = 2048

StreamName = Literal["stdout", "stderr", "system"]


@dataclass
class OutputChunk:
    """One incremental output frame."""

    tool_call_id: str
    stream: str  # stdout | stderr | system
    data: str
    seq: int
    ts: float = field(default_factory=time.time)
    tool_name: str = ""
    source: str = "shell"  # shell | code | dev_server
    done: bool = False
    exit_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "tool_call_id": self.tool_call_id,
            "stream": self.stream,
            "data": self.data,
            "seq": self.seq,
            "ts": self.ts,
            "tool_name": self.tool_name,
            "source": self.source,
        }
        if self.done:
            out["done"] = True
            out["exit_code"] = self.exit_code
        return out


class _CallBuffer:
    """Bounded tail buffer for one tool call's combined output."""

    __slots__ = ("chunks", "total_bytes", "truncated_head", "tool_name", "source", "closed")

    def __init__(self, tool_name: str, source: str) -> None:
        self.chunks: list[tuple[str, str]] = []  # (stream, data)
        self.total_bytes = 0
        self.truncated_head = False
        self.tool_name = tool_name
        self.source = source
        self.closed = False

    def append(self, stream: str, data: str) -> None:
        self.chunks.append((stream, data))
        self.total_bytes += len(data)
        while self.total_bytes > _BACKLOG_LIMIT and self.chunks:
            _, dropped = self.chunks.pop(0)
            self.total_bytes -= len(dropped)
            self.truncated_head = True

    def text(self, stream: str | None = None) -> str:
        return "".join(d for s, d in self.chunks if stream is None or s == stream)


class ToolOutputBus:
    """Session-scoped pub/sub for live subprocess output."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[asyncio.Queue[OutputChunk]]] = {}
        self._backlog: dict[str, OrderedDict[str, _CallBuffer]] = {}
        self._seq = 0

    # -- producer ---------------------------------------------------------

    def publish(
        self,
        session_id: str | None,
        tool_call_id: str,
        stream: str,
        data: str,
        *,
        tool_name: str = "",
        source: str = "shell",
        done: bool = False,
        exit_code: int | None = None,
    ) -> None:
        """Record a chunk and fan it out to session subscribers (non-blocking)."""
        if session_id is None or not tool_call_id:
            return
        sid = str(session_id)
        with self._lock:
            self._seq += 1
            chunk = OutputChunk(
                tool_call_id=tool_call_id,
                stream=stream,
                data=data,
                seq=self._seq,
                tool_name=tool_name,
                source=source,
                done=done,
                exit_code=exit_code,
            )
            calls = self._backlog.setdefault(sid, OrderedDict())
            buf = calls.get(tool_call_id)
            if buf is None:
                buf = _CallBuffer(tool_name, source)
                calls[tool_call_id] = buf
                calls.move_to_end(tool_call_id)
                while len(calls) > _MAX_CALLS:
                    calls.popitem(last=False)
            if data:
                buf.append(stream, data)
            if done:
                buf.closed = True
            queues = list(self._subscribers.get(sid, ()))

        for q in queues:
            try:
                q.put_nowait(chunk)
            except asyncio.QueueFull:
                # Slow consumer: drop rather than stall the subprocess reader.
                pass

    # -- consumer ---------------------------------------------------------

    async def subscribe(self, session_id: str) -> AsyncIterator[OutputChunk]:
        """Yield chunks for a session until the consumer disconnects."""
        sid = str(session_id)
        q: asyncio.Queue[OutputChunk] = asyncio.Queue(maxsize=_QUEUE_CAPACITY)
        with self._lock:
            self._subscribers.setdefault(sid, set()).add(q)
        try:
            while True:
                chunk = await q.get()
                yield chunk
        finally:
            with self._lock:
                subs = self._subscribers.get(sid)
                if subs is not None:
                    subs.discard(q)
                    if not subs:
                        self._subscribers.pop(sid, None)

    # -- retrieval ---------------------------------------------------------

    def get_full_output(
        self, session_id: str, tool_call_id: str,
    ) -> dict[str, Any] | None:
        """Return the retained tail of one call's output (or ``None``)."""
        with self._lock:
            buf = self._backlog.get(str(session_id), {}).get(tool_call_id)
            if buf is None:
                return None
            return {
                "tool_call_id": tool_call_id,
                "tool_name": buf.tool_name,
                "source": buf.source,
                "stdout": buf.text("stdout"),
                "stderr": buf.text("stderr"),
                "combined": buf.text(),
                "truncated_head": buf.truncated_head,
                "closed": buf.closed,
                "total_bytes": buf.total_bytes,
            }

    def list_calls(self, session_id: str) -> list[dict[str, Any]]:
        """Summaries of retained calls for a session (most recent last)."""
        with self._lock:
            calls = self._backlog.get(str(session_id), {})
            return [
                {
                    "tool_call_id": cid,
                    "tool_name": buf.tool_name,
                    "source": buf.source,
                    "total_bytes": buf.total_bytes,
                    "truncated_head": buf.truncated_head,
                    "closed": buf.closed,
                }
                for cid, buf in calls.items()
            ]

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._backlog.pop(str(session_id), None)


_BUS: ToolOutputBus | None = None


def get_tool_output_bus() -> ToolOutputBus:
    global _BUS
    if _BUS is None:
        _BUS = ToolOutputBus()
    return _BUS


def reset_tool_output_bus() -> None:
    """Testing hook."""
    global _BUS
    _BUS = None
