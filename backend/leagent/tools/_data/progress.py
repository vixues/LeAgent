"""Structured, throttled progress reporting for long-running tools.

:class:`ProgressReporter` wraps the optional ``on_progress`` callback
that :class:`~leagent.tools.executor.ToolExecutor` passes into
:meth:`BaseTool.run`. Tools call :meth:`report` after each chunk; the
reporter coalesces events so we don't flood workflow UI / logs with one
message per row.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

__all__ = ["ProgressReporter", "ProgressEvent"]


@dataclass
class ProgressEvent:
    """Structured progress event emitted via the callback."""

    tool: str
    stage: str
    processed: int
    total: int | None
    elapsed_ms: int
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "tool_progress",
            "tool": self.tool,
            "stage": self.stage,
            "processed": self.processed,
            "total": self.total,
            "elapsed_ms": self.elapsed_ms,
            "message": self.message,
            "percent": (
                int(100 * self.processed / self.total)
                if self.total and self.total > 0
                else None
            ),
        }


class ProgressReporter:
    """Emit progress events with rate-limiting.

    Parameters
    ----------
    callback
        The underlying on-progress callback (may be ``None``).
    tool
        Tool name for correlation.
    throttle_ms
        Minimum milliseconds between emitted events. A ``0`` value
        forwards every ``report`` call.
    """

    def __init__(
        self,
        callback: Callable[[dict[str, Any]], None] | None,
        *,
        tool: str,
        throttle_ms: int = 250,
    ) -> None:
        self._callback = callback
        self._tool = tool
        self._throttle_ms = throttle_ms
        self._started_at = time.monotonic()
        self._last_emit: float = 0.0
        self._processed = 0

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._started_at) * 1000)

    def advance(self, n: int = 1) -> None:
        """Increase the processed counter without forcing an emit."""
        self._processed += n

    def report(
        self,
        *,
        stage: str,
        total: int | None = None,
        processed: int | None = None,
        message: str | None = None,
        force: bool = False,
    ) -> None:
        """Emit a progress event if the throttle allows it."""
        if self._callback is None:
            return
        if processed is not None:
            self._processed = processed
        now = time.monotonic()
        if not force and self._last_emit and \
                (now - self._last_emit) * 1000 < self._throttle_ms:
            return
        self._last_emit = now
        event = ProgressEvent(
            tool=self._tool,
            stage=stage,
            processed=self._processed,
            total=total,
            elapsed_ms=self.elapsed_ms,
            message=message,
        )
        try:
            self._callback(event.to_dict())
        except Exception:  # noqa: BLE001
            # Progress callbacks must never break tool execution.
            pass

    def finish(self, *, stage: str = "done", message: str | None = None,
               total: int | None = None) -> None:
        """Emit a final event regardless of throttling."""
        self.report(stage=stage, total=total, message=message, force=True)
