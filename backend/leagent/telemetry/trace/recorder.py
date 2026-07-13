"""Best-effort observer that records durable agent running traces.

Mirrors Codex / Hermes: never raise into the hot path; append-only spine
with optional out-of-line payloads.

Hot-path cost is kept low by:
* fire-and-forget scheduling (never await on the agent loop)
* coalescing create / span / counter updates into one DB transaction per flush
* skipping I/O previews unless ``LEAGENT_TRACE_RECORD_PREVIEWS`` (or payloads) is on
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from leagent.config.constants import TRACES_DIR
from leagent.db.models.base import _naive_utc_now
from leagent.telemetry.trace.context import (
    bind_trace_context,
    clear_trace_context,
    current_run_id,
    parent_span_id_var,
    root_span_id_var,
)
from leagent.telemetry.trace.models import (
    new_span_id,
    prompt_hash,
    truncate_preview,
)
from leagent.telemetry.trace.store import TraceStore, get_trace_store
from leagent.utils.logging import get_logger

logger = get_logger(__name__)


def _settings() -> Any:
    try:
        from leagent.config import get_settings

        return get_settings().trace
    except Exception:
        return None


def _enabled() -> bool:
    cfg = _settings()
    return True if cfg is None else bool(getattr(cfg, "enabled", True))


def _preview_chars() -> int:
    cfg = _settings()
    return int(getattr(cfg, "preview_chars", 512) if cfg else 512)


def _capture_payloads() -> bool:
    cfg = _settings()
    return bool(getattr(cfg, "capture_payloads", False) if cfg else False)


def _record_previews() -> bool:
    """Store input/output preview text on spans (heavier). Off by default."""
    cfg = _settings()
    if cfg is None:
        return False
    if bool(getattr(cfg, "capture_payloads", False)):
        return True
    return bool(getattr(cfg, "record_previews", False))


def _flush_interval_ms() -> int:
    cfg = _settings()
    return int(getattr(cfg, "flush_interval_ms", 50) if cfg else 50)


def _utcnow() -> datetime:
    return _naive_utc_now()


def _schedule(coro: Any) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(coro)

    def _done(t: asyncio.Task[Any]) -> None:
        try:
            t.result()
        except Exception:
            logger.warning("agent_trace_task_failed", exc_info=True)

    task.add_done_callback(_done)


def _maybe_preview(value: Any) -> str | None:
    if not _record_previews() or value is None:
        return None
    return truncate_preview(value, _preview_chars())


@dataclass
class _PendingBuf:
    """In-memory ops for one trace, flushed as a single DB transaction."""

    create: dict[str, Any] | None = None
    spans: list[dict[str, Any]] = field(default_factory=list)
    closes: list[dict[str, Any]] = field(default_factory=list)
    update: dict[str, Any] = field(default_factory=dict)


class TraceRecorder:
    """In-process recorder keyed by ``run_id`` (= ``trace_id``)."""

    def __init__(self, store: TraceStore | None = None) -> None:
        self._store = store or get_trace_store()
        self._seq: dict[str, int] = {}
        self._open_tools: dict[str, dict[str, str]] = {}
        self._started_at: dict[str, datetime] = {}
        self._root_span: dict[str, str] = {}
        self._ended: set[str] = set()
        self._pending: dict[str, _PendingBuf] = {}
        self._flush_handle: asyncio.TimerHandle | None = None
        self._flushing = False

    def _next_seq(self, trace_id: str) -> int:
        n = self._seq.get(trace_id, 0) + 1
        self._seq[trace_id] = n
        return n

    def _buf(self, trace_id: str) -> _PendingBuf:
        buf = self._pending.get(trace_id)
        if buf is None:
            buf = _PendingBuf()
            self._pending[trace_id] = buf
        return buf

    def _merge_update(self, buf: _PendingBuf, **kwargs: Any) -> None:
        upd = buf.update
        for key, val in kwargs.items():
            if key.startswith("incr_") and isinstance(val, (int, float)):
                upd[key] = type(val)(upd.get(key, 0) + val)
            elif val is not None:
                upd[key] = val

    def _schedule_flush(self, *, force: bool = False) -> None:
        if force or _flush_interval_ms() <= 0:
            if self._flush_handle is not None:
                self._flush_handle.cancel()
                self._flush_handle = None
            _schedule(self._flush_pending())
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._flush_handle is not None:
            return
        delay = max(0.0, _flush_interval_ms() / 1000.0)

        def _fire() -> None:
            self._flush_handle = None
            _schedule(self._flush_pending())

        self._flush_handle = loop.call_later(delay, _fire)

    async def flush(self) -> None:
        """Public awaitable flush (tests / shutdown)."""
        if self._flush_handle is not None:
            self._flush_handle.cancel()
            self._flush_handle = None
        await self._flush_pending()

    async def _flush_pending(self) -> None:
        if self._flushing:
            return
        if not self._pending:
            return
        self._flushing = True
        try:
            # Snapshot + clear so new events can enqueue while we write.
            batch = self._pending
            self._pending = {}
            for tid, buf in batch.items():
                await self._flush_one(tid, buf)
        finally:
            self._flushing = False
            # A concurrent enqueue may have filled _pending again.
            if self._pending:
                self._schedule_flush(force=True)

    async def _flush_one(self, tid: str, buf: _PendingBuf) -> None:
        write_batch = getattr(self._store, "write_batch", None)
        if callable(write_batch):
            await write_batch(
                create=buf.create,
                spans=buf.spans,
                closes=buf.closes,
                update={"trace_id": tid, **buf.update} if buf.update else None,
            )
            return
        # Fallback for in-memory test stores without write_batch.
        if buf.create:
            await self._store.create_trace(**buf.create)
        for span in buf.spans:
            await self._store.append_span(**span)
        for close in buf.closes:
            span_id = close.pop("span_id")
            await self._store.close_span(span_id, **close)
        if buf.update:
            await self._store.update_trace(tid, **buf.update)

    def start_trace(
        self,
        *,
        run_id: str,
        scope: str = "chat_turn",
        session_id: str | None = None,
        user_id: str | None = None,
        parent_run_id: str | None = None,
        agent_name: str = "",
        model: str = "",
        experiment_id: str | None = None,
        prompt: str | None = None,
        tags: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not _enabled() or not run_id:
            return
        self._ended.discard(run_id)
        meta = dict(metadata or {})
        if not agent_name:
            agent_name = str(meta.get("agent_name") or meta.get("agent_id") or "")
        if not model:
            model = str(meta.get("model") or "")
        if experiment_id is None:
            experiment_id = meta.get("experiment_id")
        if tags is None and isinstance(meta.get("tags"), dict):
            tags = meta["tags"]
        root_id = new_span_id()
        self._root_span[run_id] = root_id
        self._started_at[run_id] = _utcnow()
        self._open_tools[run_id] = {}
        self._seq[run_id] = 0
        bind_trace_context(run_id=run_id, root_span_id=root_id, parent_span_id=root_id)
        ph = prompt_hash(prompt) if prompt else meta.get("prompt_hash")
        started = self._started_at[run_id]

        buf = self._buf(run_id)
        buf.create = {
            "trace_id": run_id,
            "parent_trace_id": parent_run_id,
            "session_id": session_id,
            "user_id": user_id,
            "scope": scope,
            "agent_name": agent_name,
            "model": model,
            "experiment_id": str(experiment_id) if experiment_id else None,
            "prompt_hash": str(ph) if ph else None,
            "tags": tags,
            "root_span_id": root_id,
            "started_at": started,
        }
        buf.spans.append(
            {
                "span_id": root_id,
                "parent_span_id": None,
                "trace_id": run_id,
                "seq": self._next_seq(run_id),
                "kind": "agent",
                "name": agent_name or f"agent.{scope}",
                "status": "running",
                "started_at": started,
                "attrs": {
                    "scope": scope,
                    "openinference.span.kind": "AGENT",
                    "gen_ai.operation.name": "invoke_agent",
                },
                "input_preview": _maybe_preview(prompt),
            }
        )
        # Persist header promptly so session list APIs see the run.
        self._schedule_flush(force=True)

    def end_trace(
        self,
        run_id: str | None = None,
        *,
        status: str = "completed",
        terminal_reason: str | None = None,
        error: str | None = None,
    ) -> None:
        if not _enabled():
            return
        tid = run_id or current_run_id()
        if not tid:
            return
        if tid in self._ended:
            if current_run_id() == tid:
                clear_trace_context()
            return
        self._ended.add(tid)
        started = self._started_at.pop(tid, None)
        ended = _utcnow()
        latency = 0.0
        if started is not None:
            latency = max(0.0, (ended - started).total_seconds() * 1000.0)
        root_id = self._root_span.pop(tid, None)
        self._open_tools.pop(tid, None)
        self._seq.pop(tid, None)

        buf = self._buf(tid)
        if root_id:
            buf.closes.append(
                {
                    "span_id": root_id,
                    "status": "error" if error or status == "error" else "ok",
                    "ended_at": ended,
                    "latency_ms": latency,
                }
            )
        self._merge_update(
            buf,
            status=status,
            terminal_reason=terminal_reason,
            ended_at=ended,
            latency_ms=latency,
            error=error,
        )
        self._schedule_flush(force=True)
        if current_run_id() == tid:
            clear_trace_context()

    def on_event(self, event: Any) -> None:
        """Map an :class:`~leagent.sdk.events.AgentEvent` onto spans."""
        if not _enabled():
            return
        tid = current_run_id()
        if not tid:
            return
        try:
            etype = getattr(event, "type", None) or ""
            data = getattr(event, "data", None) or {}
            if not isinstance(data, dict):
                data = {}
            if etype in ("tool_use", "assistant_tools"):
                if etype == "assistant_tools":
                    tools = data.get("tool_calls") or data.get("tools") or []
                    if isinstance(tools, list):
                        for tc in tools:
                            if isinstance(tc, dict):
                                self._open_tool_from_dict(tid, tc)
                    return
                self._open_tool_from_dict(tid, data)
            elif etype == "tool_result":
                self._close_tool_from_dict(tid, data)
            elif etype == "result":
                reason = str(data.get("reason") or "completed")
                err = data.get("error")
                status = "error" if err or reason in {"model_error", "error"} else "completed"
                if reason == "awaiting_user_input":
                    status = "paused"
                self.end_trace(
                    tid,
                    status=status,
                    terminal_reason=reason,
                    error=str(err) if err else None,
                )
            elif etype == "stream_delta" and data.get("error"):
                self._record_error_span(tid, str(data.get("error")))
        except Exception:
            logger.debug("agent_trace_on_event_failed", exc_info=True)

    def _open_tool_from_dict(self, tid: str, data: dict[str, Any]) -> None:
        call_id = str(
            data.get("id")
            or data.get("tool_call_id")
            or data.get("tool_use_id")
            or ""
        )
        name = str(data.get("name") or "tool")
        if not call_id:
            call_id = new_span_id()
        open_map = self._open_tools.setdefault(tid, {})
        if call_id in open_map:
            return
        span_id = new_span_id()
        open_map[call_id] = span_id
        args = data.get("input") if isinstance(data.get("input"), dict) else data.get("arguments")
        parent = root_span_id_var.get() or self._root_span.get(tid)
        payload_ref = self._maybe_write_payload(tid, span_id, {"input": args}) if args else None
        buf = self._buf(tid)
        buf.spans.append(
            {
                "span_id": span_id,
                "parent_span_id": parent,
                "trace_id": tid,
                "seq": self._next_seq(tid),
                "kind": "tool",
                "name": f"tool.{name}",
                "status": "running",
                "attrs": {
                    "tool.name": name,
                    "tool.call_id": call_id,
                    "openinference.span.kind": "TOOL",
                    "gen_ai.operation.name": "execute_tool",
                },
                "input_preview": _maybe_preview(args),
                "payload_ref": payload_ref,
            }
        )
        self._merge_update(buf, incr_tool_call_count=1)
        self._schedule_flush()

    def _close_tool_from_dict(self, tid: str, data: dict[str, Any]) -> None:
        call_id = str(
            data.get("tool_use_id")
            or data.get("tool_call_id")
            or data.get("id")
            or ""
        )
        open_map = self._open_tools.get(tid) or {}
        span_id = open_map.pop(call_id, None) if call_id else None
        success = bool(data.get("success", True))
        content = data.get("content")
        if content is None:
            content = data.get("data")
        err = data.get("error")
        duration = float(data.get("duration_ms") or 0.0)
        payload_ref = (
            self._maybe_write_payload(
                tid, span_id or call_id or "tool", {"output": content, "error": err}
            )
            if content is not None or err
            else None
        )
        # Always keep a short error preview even when record_previews is off.
        out_preview = None
        if err:
            out_preview = truncate_preview(str(err), _preview_chars())
        elif _record_previews():
            out_preview = truncate_preview(content, _preview_chars())

        buf = self._buf(tid)
        if span_id:
            buf.closes.append(
                {
                    "span_id": span_id,
                    "status": "error" if not success or err else "ok",
                    "latency_ms": duration,
                    "attrs": {"tool.success": success, "error": str(err) if err else None},
                    "output_preview": out_preview,
                    "payload_ref": payload_ref,
                }
            )
        else:
            parent = root_span_id_var.get() or self._root_span.get(tid)
            buf.spans.append(
                {
                    "span_id": new_span_id(),
                    "parent_span_id": parent,
                    "trace_id": tid,
                    "seq": self._next_seq(tid),
                    "kind": "tool",
                    "name": f"tool.{data.get('name') or 'unknown'}",
                    "status": "error" if not success or err else "ok",
                    "latency_ms": duration,
                    "attrs": {
                        "tool.name": data.get("name"),
                        "tool.call_id": call_id,
                        "tool.success": success,
                    },
                    "output_preview": out_preview,
                    "payload_ref": payload_ref,
                }
            )
        self._schedule_flush()

    def _record_error_span(self, tid: str, message: str) -> None:
        parent = root_span_id_var.get() or self._root_span.get(tid)
        buf = self._buf(tid)
        buf.spans.append(
            {
                "span_id": new_span_id(),
                "parent_span_id": parent,
                "trace_id": tid,
                "seq": self._next_seq(tid),
                "kind": "error",
                "name": "error",
                "status": "error",
                "ended_at": _utcnow(),
                "attrs": {"error.message": message[:1000]},
                "output_preview": truncate_preview(message, _preview_chars()),
            }
        )
        self._schedule_flush()

    def record_llm(
        self,
        *,
        provider: str,
        model: str,
        request_model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_miss_tokens: int = 0,
        total_cost_usd: float = 0.0,
        latency_ms: float = 0.0,
        ttfb_ms: float = 0.0,
        status_code: int = 200,
        error: str | None = None,
        is_streaming: bool = False,
        call_index: int = 0,
        call_kind: str = "chat",
        run_id: str | None = None,
    ) -> None:
        if not _enabled():
            return
        tid = run_id or current_run_id()
        if not tid:
            return
        parent = root_span_id_var.get() or self._root_span.get(tid)
        span_id = new_span_id()
        seq = self._next_seq(tid)
        ok = status_code < 400 and not error
        ended = _utcnow()
        # Keep attrs compact — enough for eval / Admin, no large blobs.
        attrs: dict[str, Any] = {
            "gen_ai.provider.name": provider,
            "gen_ai.request.model": request_model or model,
            "gen_ai.response.model": model,
            "gen_ai.usage.input_tokens": input_tokens,
            "gen_ai.usage.output_tokens": output_tokens,
            "openinference.span.kind": "LLM",
            "latency_ms": latency_ms,
            "status_code": status_code,
            "call_kind": call_kind,
        }
        if cache_read_tokens or cache_miss_tokens:
            attrs["gen_ai.usage.cache_read_tokens"] = cache_read_tokens
            attrs["gen_ai.usage.cache_miss_tokens"] = cache_miss_tokens
        if ttfb_ms:
            attrs["ttfb_ms"] = ttfb_ms
        if total_cost_usd:
            attrs["total_cost_usd"] = total_cost_usd
        if is_streaming:
            attrs["is_streaming"] = True
        if call_index:
            attrs["call_index"] = call_index
        if error:
            attrs["error"] = error

        buf = self._buf(tid)
        buf.spans.append(
            {
                "span_id": span_id,
                "parent_span_id": parent,
                "trace_id": tid,
                "seq": seq,
                "kind": "llm",
                "name": f"llm.{model or request_model or 'unknown'}",
                "status": "ok" if ok else "error",
                "started_at": ended,
                "ended_at": ended,
                "latency_ms": latency_ms,
                "attrs": attrs,
                "output_preview": truncate_preview(error, _preview_chars()) if error else None,
            }
        )
        self._merge_update(
            buf,
            model=model or request_model or None,
            incr_input_tokens=input_tokens,
            incr_output_tokens=output_tokens,
            incr_cache_read_tokens=cache_read_tokens,
            incr_cache_miss_tokens=cache_miss_tokens,
            incr_total_cost_usd=total_cost_usd,
            incr_llm_call_count=1,
        )
        self._schedule_flush()

    def record_compact(self, reason: str) -> None:
        if not _enabled():
            return
        tid = current_run_id()
        if not tid:
            return
        parent = root_span_id_var.get() or self._root_span.get(tid)
        buf = self._buf(tid)
        buf.spans.append(
            {
                "span_id": new_span_id(),
                "parent_span_id": parent,
                "trace_id": tid,
                "seq": self._next_seq(tid),
                "kind": "compact",
                "name": "compact",
                "status": "ok",
                "ended_at": _utcnow(),
                "attrs": {"reason": reason},
            }
        )
        self._schedule_flush()

    def record_subagent(
        self,
        *,
        agent_name: str,
        phase: str,
        prompt: str | None = None,
        result_preview: str | None = None,
    ) -> None:
        if not _enabled():
            return
        tid = current_run_id()
        if not tid:
            return
        parent = root_span_id_var.get() or self._root_span.get(tid)
        buf = self._buf(tid)
        buf.spans.append(
            {
                "span_id": new_span_id(),
                "parent_span_id": parent,
                "trace_id": tid,
                "seq": self._next_seq(tid),
                "kind": "subagent",
                "name": f"subagent.{agent_name}.{phase}",
                "status": "ok",
                "ended_at": _utcnow(),
                "attrs": {"agent_name": agent_name, "phase": phase},
                "input_preview": _maybe_preview(prompt),
                "output_preview": _maybe_preview(result_preview),
            }
        )
        self._schedule_flush()

    def _maybe_write_payload(
        self, trace_id: str, span_id: str, payload: dict[str, Any]
    ) -> str | None:
        if not _capture_payloads():
            return None
        try:
            directory = Path(TRACES_DIR) / trace_id
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{span_id}.json"
            path.write_text(
                json.dumps(payload, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            return str(path)
        except Exception:
            logger.debug("agent_trace_payload_write_failed", exc_info=True)
            return None


_recorder: TraceRecorder | None = None


def get_trace_recorder() -> TraceRecorder:
    global _recorder
    if _recorder is None:
        _recorder = TraceRecorder()
    return _recorder


__all__ = ["TraceRecorder", "get_trace_recorder"]
