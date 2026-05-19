"""Shared helpers for building a fully-populated :class:`ToolContext`.

The tool framework defines :class:`~leagent.tools.base.ToolContext` with
slots for DB, Redis, MinIO, LLM, abort signal, and an ``extra`` bag. This
module is the single place that knows how to snap those slots to the
running :class:`~leagent.services.service_manager.ServiceManager` so
agents, workflows, the MCP bridge, and background workers all hand tools
the same shape.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from leagent.tools.base import ToolContext

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from leagent.services.service_manager import ServiceManager


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, UUID)):
        return str(value)
    return str(value)


def build_tool_context(
    *,
    service_manager: "ServiceManager | None" = None,
    user_id: Any = None,
    session_id: Any = None,
    task_id: Any = None,
    abort_signal: asyncio.Event | None = None,
    temp_dir: str | Path | None = None,
    extra: dict[str, Any] | None = None,
) -> ToolContext:
    """Build a rich :class:`ToolContext` wired to a :class:`ServiceManager`.

    Any missing service resolves to ``None`` so the result is safe to use
    in degraded/test environments. Callers should prefer this helper over
    constructing :class:`ToolContext` directly.
    """

    settings = getattr(service_manager, "settings", None)

    db = getattr(service_manager, "db", None) if service_manager else None
    cache = getattr(service_manager, "redis_client", None) if service_manager else None
    file_store = getattr(service_manager, "file_store", None) if service_manager else None
    llm = getattr(service_manager, "llm_service", None) if service_manager else None

    resolved_temp = None
    if temp_dir is not None:
        path = Path(temp_dir)
        path.mkdir(parents=True, exist_ok=True)
        resolved_temp = str(path)
    else:
        resolved_temp = tempfile.gettempdir()

    return ToolContext(
        user_id=_stringify(user_id),
        session_id=_stringify(session_id),
        task_id=_stringify(task_id),
        settings=settings,
        db=db,
        cache=cache,
        file_store=file_store,
        llm=llm,
        temp_dir=resolved_temp,
        abort_signal=abort_signal,
        extra=dict(extra or {}),
    )


def merge_tool_context(base: ToolContext, **overrides: Any) -> ToolContext:
    """Return a shallow copy of ``base`` with ``overrides`` applied."""
    data = {
        "user_id": base.user_id,
        "session_id": base.session_id,
        "task_id": base.task_id,
        "settings": base.settings,
        "db": base.db,
        "cache": base.cache,
        "file_store": base.file_store,
        "llm": base.llm,
        "temp_dir": base.temp_dir,
        "abort_signal": base.abort_signal,
        "extra": dict(base.extra),
    }
    data.update(overrides)
    return ToolContext(**data)


__all__ = ["build_tool_context", "merge_tool_context"]
