"""Dependency-injection container for ``query()``.

Mirrors ``./query/deps.ts``: exposes the external effects the query loop
needs (model streaming + compaction hooks) behind a Protocol so tests can
inject a fake model without monkey-patching ``LLMService``.
"""

from __future__ import annotations

import asyncio
import base64 as _b64
import binascii as _binascii
import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator, Protocol

import structlog

from leagent.llm.base import token_usage_to_api_dict
from leagent.tools.executor import parse_tool_arguments_str, strict_json_loads_error

if TYPE_CHECKING:
    from leagent.agent.tool_use_context import ToolUseContext
    from leagent.llm import LLMService

logger = structlog.get_logger(__name__)

# Throttle streamed tool JSON fragments (large canvas_publish HTML arguments).
_TOOL_CALL_DELTA_MIN_INTERVAL_MS = 48
_TOOL_CALL_DELTA_MIN_BYTE_STEP = 512
_STREAM_FIRST_EVENT_TIMEOUT_SEC = 12.0


def _partial_arguments_dict(raw: str) -> dict[str, Any] | None:
    """Return parsed tool args when ``raw`` is complete JSON; else None."""
    parsed = parse_tool_arguments_str(raw)
    return parsed if isinstance(parsed, dict) else None


def _decode_b64_tolerant(raw: str) -> str | None:
    """Decode base64, trimming trailing incomplete groups if truncated."""
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        return _b64.b64decode(stripped, validate=True).decode("utf-8")
    except (_binascii.Error, ValueError, UnicodeDecodeError):
        pass
    trimmed = stripped[: len(stripped) - (len(stripped) % 4)]
    if len(trimmed) < 4:
        return None
    try:
        return _b64.b64decode(trimmed, validate=True).decode("utf-8")
    except (_binascii.Error, ValueError, UnicodeDecodeError):
        try:
            return _b64.b64decode(trimmed).decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            return None


def _ingest_session_id(session_id: str | None) -> str:
    """Normalize session id for blob ingest (matches ``_session_key``)."""
    sid = str(session_id or "").strip()
    return sid or "__no_session__"


async def _try_blob_streaming_ingest(
    tool_name: str,
    raw_args: str,
    *,
    session_id: str | None = None,
) -> dict[str, Any] | None:
    """Salvage a broken ``tool_argument_blob`` append by ingesting directly.

    When JSON parsing fails for a ``tool_argument_blob`` call, we extract
    the chunk content from the raw argument string and deposit it into the
    blob store, returning a synthetic arguments dict with
    ``_chunk_ingested=True`` so the tool's ``execute()`` skips the
    redundant append.
    """
    if tool_name != "tool_argument_blob":
        return None
    low = raw_args.lower()
    is_append = '"append"' in low
    is_caf = '"create_and_finalize"' in low
    if not is_append and not is_caf:
        return None

    from leagent.tools.executor import _recover_tool_argument_blob_args

    recovered = _recover_tool_argument_blob_args(raw_args)
    if recovered is None:
        return None

    b64_str = recovered.get("chunk_base64", "")
    if not b64_str:
        return None

    chunk_text = _decode_b64_tolerant(b64_str)
    if chunk_text is None:
        return None

    action = recovered.get("action", "append")
    blob_id = recovered.get("blob_id", "")

    from leagent.tools.util.tool_argument_blob import ToolArgumentBlobStore

    ingest_sid = _ingest_session_id(session_id)
    n_bytes = len(chunk_text.encode("utf-8"))

    if action == "create_and_finalize":
        # Check whether this was salvaged from a truncated base64 string
        # (original b64 didn't decode cleanly and we had to trim).
        was_truncated = False
        try:
            _b64.b64decode(b64_str.strip(), validate=True).decode("utf-8")
        except Exception:  # noqa: BLE001
            was_truncated = True

        new_id = await ToolArgumentBlobStore.create(ingest_sid)
        result = await ToolArgumentBlobStore.append(ingest_sid, new_id, chunk_text)
        if not result.get("ok"):
            return None

        if was_truncated:
            # Partial content saved but NOT finalized — the LLM should
            # continue appending via action=append and then finalize.
            logger.info(
                "blob_streaming_ingest_partial_create",
                blob_id=new_id,
                bytes=n_bytes,
                truncated=True,
            )
            return {
                "action": "create_and_finalize",
                "blob_id": new_id,
                "_chunk_ingested": True,
                "_ingested_bytes": n_bytes,
                "_truncated": True,
            }

        await ToolArgumentBlobStore.finalize(ingest_sid, new_id)
        logger.info(
            "blob_streaming_ingest_create_and_finalize",
            blob_id=new_id,
            bytes=n_bytes,
        )
        return {
            "action": "create_and_finalize",
            "blob_id": new_id,
            "_chunk_ingested": True,
            "_ingested_bytes": n_bytes,
        }

    if not blob_id:
        return None
    real_sid = await ToolArgumentBlobStore.find_session_for_blob(blob_id)
    if real_sid is None:
        return None
    result = await ToolArgumentBlobStore.append(real_sid, blob_id, chunk_text)
    if not result.get("ok"):
        return None

    logger.info(
        "blob_streaming_ingest",
        blob_id=blob_id,
        bytes=n_bytes,
    )
    return {
        "action": "append",
        "blob_id": blob_id,
        "_chunk_ingested": True,
        "_ingested_bytes": n_bytes,
    }


_DIRECT_INGEST_TOOLS: dict[str, tuple[str, str]] = {
    "project_write": ("content", "content_blob_id"),
    "project_edit": ("new_string", "new_string_blob_id"),
    "code_execution": ("source", "source_blob_id"),
    "canvas_publish": ("html", "html_blob_id"),
}


_DIRECT_INGEST_RECOVER_FNS: dict[str, Any] | None = None


def _get_direct_ingest_recover_fn(tool_name: str) -> Any:
    """Return the recovery function for a direct-ingest tool (cached)."""
    global _DIRECT_INGEST_RECOVER_FNS  # noqa: PLW0603
    if _DIRECT_INGEST_RECOVER_FNS is None:
        from leagent.tools.executor import (
            _recover_canvas_publish_args,
            _recover_code_execution_args,
            _recover_project_edit_args,
            _recover_project_write_args,
        )

        _DIRECT_INGEST_RECOVER_FNS = {
            "project_write": _recover_project_write_args,
            "project_edit": _recover_project_edit_args,
            "code_execution": _recover_code_execution_args,
            "canvas_publish": _recover_canvas_publish_args,
        }
    return _DIRECT_INGEST_RECOVER_FNS.get(tool_name)


async def _try_direct_content_ingest(
    tool_name: str,
    raw_args: str,
    *,
    session_id: str | None = None,
) -> dict[str, Any] | None:
    """Salvage broken tool calls by auto-staging their content field as a blob.

    When JSON parsing fails because the large text field (``content``,
    ``source``, or ``html``) contains unescaped characters, we extract the
    field using the executor's per-tool recovery helpers and stage it into a
    finalized blob, then return a synthetic args dict with the matching
    ``*_blob_id`` so the tool consumes the content without the LLM needing
    to go through the multi-step ``tool_argument_blob`` flow.

    Supported tools: ``project_write``, ``project_edit``, ``code_execution``,
    ``canvas_publish``.
    """
    spec = _DIRECT_INGEST_TOOLS.get(tool_name)
    if spec is None:
        return None
    content_key, blob_key = spec

    recover_fn = _get_direct_ingest_recover_fn(tool_name)
    if recover_fn is None:
        return None
    recovered = recover_fn(raw_args)
    if recovered is None:
        return None
    content = recovered.get(content_key)
    if not isinstance(content, str) or not content.strip():
        return None

    from leagent.tools.util.tool_argument_blob import ToolArgumentBlobStore

    ingest_sid = _ingest_session_id(session_id)
    blob_id = await ToolArgumentBlobStore.create(ingest_sid)
    append_result = await ToolArgumentBlobStore.append(ingest_sid, blob_id, content)
    if not append_result.get("ok"):
        await ToolArgumentBlobStore.discard(ingest_sid, blob_id)
        return None
    await ToolArgumentBlobStore.finalize(ingest_sid, blob_id)

    n_bytes = len(content.encode("utf-8"))
    logger.info(
        "direct_content_ingest",
        tool=tool_name,
        blob_id=blob_id,
        bytes=n_bytes,
    )
    result = dict(recovered)
    result.pop(content_key, None)
    result[blob_key] = blob_id
    return result


def _try_salvage_truncated_ui_tree(
    tool_name: str, raw_args: str,
) -> dict[str, Any] | None:
    """Salvage a truncated ``emit_ui_tree`` call by closing open brackets.

    When the model hits ``finish_reason=length`` mid-tree, standard JSON
    parsing fails but the prefix is structurally sound. We close the
    brackets and pass whatever partial tree we recovered so the user sees
    *something* rather than an opaque ``__raw__`` error.
    """
    if tool_name != "emit_ui_tree":
        return None
    from leagent.tools.executor import _recover_emit_ui_tree_args

    recovered = _recover_emit_ui_tree_args(raw_args)
    if recovered is None:
        return None
    logger.info(
        "emit_ui_tree_truncation_salvaged",
        tree_keys=sorted(recovered.get("tree", {}).keys())[:10],
        raw_len=len(raw_args),
    )
    return recovered


def _tool_call_delta_payload(idx: int, slot: dict[str, Any]) -> dict[str, Any]:
    args_str = slot.get("arguments") or ""
    if not isinstance(args_str, str):
        args_str = ""
    tid = str(slot.get("id") or "").strip()
    name = str(slot.get("name") or "").strip()
    payload: dict[str, Any] = {
        "index": idx,
        "arguments_raw": args_str,
    }
    if tid:
        payload["id"] = tid
    if name:
        payload["name"] = name
    partial = _partial_arguments_dict(args_str)
    if partial is not None:
        payload["arguments_partial"] = partial
    return payload


def _should_emit_tool_delta(
    idx: int,
    args_len: int,
    last_emit: dict[int, dict[str, Any]],
) -> bool:
    rec = last_emit.get(idx)
    now = time.monotonic()
    if rec is None:
        return True
    if args_len - int(rec.get("sent_len", 0)) >= _TOOL_CALL_DELTA_MIN_BYTE_STEP:
        return True
    if (now - float(rec.get("t", 0))) * 1000 >= _TOOL_CALL_DELTA_MIN_INTERVAL_MS:
        return True
    return False


def _record_tool_delta_emit(
    idx: int,
    args_len: int,
    last_emit: dict[int, dict[str, Any]],
) -> None:
    last_emit[idx] = {"t": time.monotonic(), "sent_len": args_len}


def _is_retryable_stream_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, asyncio.TimeoutError):
        return True
    try:
        import httpx
        import httpcore

        if isinstance(exc, (httpx.RemoteProtocolError, httpcore.RemoteProtocolError)):
            return True
        if isinstance(exc, (httpx.ReadError, httpcore.ReadError)):
            return True
    except ImportError:
        pass
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "incomplete chunked read",
            "peer closed connection",
            "connection reset",
            "remote protocol error",
        )
    )


# ---------------------------------------------------------------------------
# Stream event produced by ``deps.call_model``
# ---------------------------------------------------------------------------


@dataclass
class MessageStopInfo:
    """Typed builder for the ``message_stop`` payload in ``ModelStreamEvent``.

    Centralises key names so construction sites cannot introduce typos.
    Call ``to_dict()`` to produce the plain dict that consumers expect.
    """

    finish_reason: str = "stop"
    usage: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    error: str | None = None
    warning: str | None = None
    fallback: str | None = None
    partial: bool = False
    resource_exhausted: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "model": self.model,
        }
        if self.error is not None:
            d["error"] = self.error
        if self.warning is not None:
            d["warning"] = self.warning
        if self.fallback is not None:
            d["fallback"] = self.fallback
        if self.partial:
            d["partial"] = True
        if self.resource_exhausted:
            d["resource_exhausted"] = True
        return d


@dataclass
class ModelStreamEvent:
    """Normalised event emitted by a model stream.

    Typically ``content_delta`` and/or ``reasoning_delta`` during the stream,
    then ``tool_call`` events, then ``message_stop``.

    Fields:
        content_delta: Text appended to the assistant message.
        reasoning_delta: Fragment of model ``reasoning_content`` (thinking mode).
        tool_call: Finalised tool-call dict (``{"id","name","arguments":{...}}``).
        tool_call_delta: Incremental tool-call JSON fragment for UI (throttled).
        message_stop: Final frame with ``finish_reason`` + ``usage``.
        raw: Underlying provider chunk (for debugging / telemetry).
    """

    content_delta: str | None = None
    reasoning_delta: str | None = None
    tool_call: dict[str, Any] | None = None
    tool_call_delta: dict[str, Any] | None = None
    message_stop: dict[str, Any] | None = None
    raw: Any = None


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class CallModel(Protocol):
    """Streaming model invocation used by the query loop."""

    def __call__(
        self,
        *,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]] | None,
        tool_use_context: "ToolUseContext",
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
    ) -> AsyncIterator[ModelStreamEvent]: ...


class Microcompact(Protocol):
    """Fine-grained compaction of tool results inside a turn (no-op fallback)."""

    async def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_use_context: "ToolUseContext",
    ) -> list[dict[str, Any]]: ...


class Autocompact(Protocol):
    """Full-history summarisation when context tokens exceed threshold."""

    async def __call__(
        self,
        messages: list[dict[str, Any]],
        tool_use_context: "ToolUseContext",
        system_prompt: str,
    ) -> list[dict[str, Any]]: ...


@dataclass
class QueryDeps:
    """Bundle of the three external effects ``query()`` needs."""

    call_model: CallModel
    microcompact: Microcompact
    autocompact: Autocompact


# ---------------------------------------------------------------------------
# Production implementations
# ---------------------------------------------------------------------------


def _normalize_fallback_tool_call(tc: dict[str, Any]) -> dict[str, Any]:
    """Unwrap an OpenAI-shaped tool-call dict to flat ``{id, name, arguments}``."""
    fn = tc.get("function") or {}
    raw_args = fn.get("arguments", tc.get("arguments", "{}"))
    if isinstance(raw_args, str):
        parsed = parse_tool_arguments_str(raw_args)
        args: dict[str, Any] = parsed if parsed is not None else {"__raw__": raw_args}
    elif isinstance(raw_args, dict):
        args = raw_args
    else:
        args = {}
    return {
        "id": tc.get("id", ""),
        "name": fn.get("name", tc.get("name", "")),
        "arguments": args,
    }


def _known_tool_names(tools: list[dict[str, Any]] | None) -> set[str]:
    names: set[str] = set()
    if not tools:
        return names
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function")
        if isinstance(fn, dict):
            name = fn.get("name")
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
        name = tool.get("name")
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return names


def _try_extract_content_tool_calls(
    content: str,
    *,
    known_tool_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Recover tool calls emitted as plain JSON in assistant ``content``.

    Some OpenAI-compatible gateways (notably vLLM + reasoning models with
    ``tool_choice=auto``) return ``{"name": "...", "arguments": {...}}`` in
    ``delta.content`` instead of structured ``tool_calls`` chunks.
    """
    text = (content or "").strip()
    if not text or '"name"' not in text:
        return []

    candidates: list[str] = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])

    seen: set[str] = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        obj: dict[str, Any] | None
        try:
            loaded = json.loads(cand)
            obj = loaded if isinstance(loaded, dict) else None
        except json.JSONDecodeError:
            parsed = parse_tool_arguments_str(cand)
            obj = parsed if isinstance(parsed, dict) else None
        if not obj:
            continue
        name_raw = obj.get("name")
        if not isinstance(name_raw, str) or not name_raw.strip():
            continue
        name = name_raw.strip()
        extra_keys = set(obj.keys()) - {"name", "arguments"}
        if extra_keys or "arguments" not in obj:
            continue
        if known_tool_names and name not in known_tool_names:
            continue
        args_raw = obj.get("arguments", {})
        if isinstance(args_raw, str):
            parsed_args = parse_tool_arguments_str(args_raw)
            args: dict[str, Any] = (
                parsed_args if parsed_args is not None else {"__raw__": args_raw}
            )
        elif isinstance(args_raw, dict):
            args = args_raw
        else:
            args = {}
        return [{"id": "call_content_0", "name": name, "arguments": args}]
    return []


async def _finalize_pending_tool_calls(
    pending_tool_calls: dict[int, dict[str, Any]],
    last_delta_emit: dict[int, dict[str, Any]],
    session_id: str | None,
) -> list[ModelStreamEvent]:
    """Emit final deltas and parsed ``tool_call`` events for coalesced calls."""
    events: list[ModelStreamEvent] = []

    for idx in sorted(pending_tool_calls.keys()):
        slot = pending_tool_calls[idx]
        args_str = slot.get("arguments")
        if not isinstance(args_str, str) or not args_str:
            continue
        rec = last_delta_emit.get(idx)
        if rec is not None and int(rec.get("sent_len", 0)) >= len(args_str):
            continue
        events.append(ModelStreamEvent(
            tool_call_delta=_tool_call_delta_payload(idx, slot),
        ))
        _record_tool_delta_emit(idx, len(args_str), last_delta_emit)

    ingest_sid = _ingest_session_id(session_id)

    for tc_idx in sorted(pending_tool_calls.keys()):
        tc = pending_tool_calls[tc_idx]
        args_str = tc.get("arguments") or "{}"
        if isinstance(args_str, dict):
            args: dict[str, Any] = args_str
        elif isinstance(args_str, str):
            parsed = parse_tool_arguments_str(args_str)
            if parsed is not None:
                args = parsed
            else:
                ingested = await _try_blob_streaming_ingest(
                    tc.get("name", ""),
                    args_str,
                    session_id=ingest_sid,
                )
                if ingested is not None:
                    args = ingested
                elif (content_ingested := await _try_direct_content_ingest(
                    tc.get("name", ""),
                    args_str,
                    session_id=ingest_sid,
                )) is not None:
                    args = content_ingested
                elif (salvaged := _try_salvage_truncated_ui_tree(
                    tc.get("name", ""), args_str,
                )) is not None:
                    args = salvaged
                else:
                    strict_err = strict_json_loads_error(args_str)
                    logger.warning(
                        "tool_call_parse_error",
                        error=str(strict_err) if strict_err else "unrecoverable_tool_arguments",
                        args_len=len(args_str),
                        json_lineno=getattr(strict_err, "lineno", None),
                        json_colno=getattr(strict_err, "colno", None),
                        json_pos=getattr(strict_err, "pos", None),
                        tool_name=tc.get("name"),
                        tool_call_index=tc_idx,
                    )
                    args = {"__raw__": args_str}
        else:
            args = {}
        events.append(ModelStreamEvent(
            tool_call={
                "id": tc["id"] or f"call_{tc_idx}",
                "name": tc["name"],
                "arguments": args,
            },
        ))

    return events


def _make_llm_call_model(llm: "LLMService") -> CallModel:
    """Wrap ``LLMService.chat_stream`` as a ``CallModel``.

    DeepSeek / OpenAI-compatible providers stream OpenAI chunks; we coalesce
    tool-call deltas (indexed by ``tool_calls[*].index``) and emit a single
    ``tool_call`` event when a ``finish_reason == "tool_calls"`` frame or the
    stream ends.
    """

    async def _call(
        *,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]] | None,
        tool_use_context: "ToolUseContext",
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
    ) -> AsyncIterator[ModelStreamEvent]:
        full_messages: list[dict[str, Any]] = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        stream_kw: dict[str, Any] = {}
        if max_output_tokens is not None:
            stream_kw["max_tokens"] = max_output_tokens
        if model_provider:
            stream_kw["provider"] = model_provider
        if model_name:
            stream_kw["model"] = model_name

        max_attempts = 3
        attempt = 0
        emitted_visible_content = False
        while True:
            attempt += 1
            pending_tool_calls: dict[int, dict[str, Any]] = {}
            last_delta_emit: dict[int, dict[str, Any]] = {}
            final_usage: dict[str, Any] = {}
            final_finish: str | None = None
            final_model: str = ""
            accumulated_content = ""

            try:
                stream_iter = llm.chat_stream(
                    messages=full_messages,
                    tools=tools,
                    tool_choice="auto" if tools else None,
                    temperature=temperature,
                    **stream_kw,
                ).__aiter__()
                saw_stream_event = False
                while True:
                    try:
                        if saw_stream_event:
                            chunk = await stream_iter.__anext__()
                        else:
                            chunk = await asyncio.wait_for(
                                stream_iter.__anext__(),
                                timeout=_STREAM_FIRST_EVENT_TIMEOUT_SEC,
                            )
                            saw_stream_event = True
                    except StopAsyncIteration:
                        break
                    except (asyncio.TimeoutError, TimeoutError):
                        await stream_iter.aclose()
                        raise TimeoutError(
                            f"Model stream produced no events within "
                            f"{_STREAM_FIRST_EVENT_TIMEOUT_SEC:.0f}s"
                        ) from None

                    reasoning_piece = (chunk.raw_delta or {}).get("reasoning_content")
                    if not isinstance(reasoning_piece, str):
                        reasoning_piece = None
                    if chunk.content or reasoning_piece:
                        if chunk.content:
                            emitted_visible_content = True
                            accumulated_content += chunk.content
                        yield ModelStreamEvent(
                            content_delta=chunk.content or None,
                            reasoning_delta=reasoning_piece,
                            raw=chunk,
                        )

                    for delta in chunk.tool_calls_delta or []:
                        idx = delta.get("index", 0)
                        slot = pending_tool_calls.setdefault(
                            idx,
                            {"id": "", "name": "", "arguments": ""},
                        )
                        if tid := delta.get("id"):
                            slot["id"] = tid
                        fn = delta.get("function") or {}
                        if fname := fn.get("name"):
                            slot["name"] = fname
                        if "arguments" in fn:
                            fargs = fn.get("arguments")
                            if isinstance(fargs, str):
                                current = slot.get("arguments")
                                if isinstance(current, str):
                                    slot["arguments"] = current + fargs
                                elif isinstance(current, dict):
                                    slot["arguments"] = json.dumps(current, ensure_ascii=False) + fargs
                                else:
                                    slot["arguments"] = fargs
                            elif isinstance(fargs, dict):
                                slot["arguments"] = fargs
                            elif fargs is not None:
                                slot["arguments"] = json.dumps(fargs, ensure_ascii=False)

                    for idx in sorted(pending_tool_calls.keys()):
                        slot = pending_tool_calls[idx]
                        args_str = slot.get("arguments")
                        if not isinstance(args_str, str) or not args_str:
                            continue
                        alen = len(args_str)
                        if not _should_emit_tool_delta(idx, alen, last_delta_emit):
                            continue
                        yield ModelStreamEvent(
                            tool_call_delta=_tool_call_delta_payload(idx, slot),
                        )
                        _record_tool_delta_emit(idx, alen, last_delta_emit)

                    if chunk.finish_reason:
                        final_finish = chunk.finish_reason
                        final_model = chunk.model or final_model

                    if chunk.usage:
                        final_usage = dict(token_usage_to_api_dict(chunk.usage))
            except Exception as exc:  # noqa: BLE001
                if (
                    attempt < max_attempts
                    and not emitted_visible_content
                    and _is_retryable_stream_error(exc)
                ):
                    logger.warning(
                        "call_model_stream_retry",
                        error=str(exc),
                        attempt=attempt,
                        max_attempts=max_attempts,
                    )
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                if not emitted_visible_content and _is_retryable_stream_error(exc):
                    logger.warning(
                        "call_model_stream_fallback_to_completion",
                        error=str(exc),
                        attempts=attempt,
                    )
                    try:
                        response = await llm.chat(
                            messages=full_messages,
                            tools=tools,
                            tool_choice="auto" if tools else None,
                            temperature=temperature,
                            **stream_kw,
                        )
                    except Exception as fallback_exc:  # noqa: BLE001
                        logger.warning(
                            "call_model_completion_fallback_error",
                            stream_error=str(exc),
                            fallback_error=str(fallback_exc),
                        )
                    else:
                        if content := response.get("content"):
                            yield ModelStreamEvent(content_delta=str(content))
                        for tc in response.get("tool_calls") or []:
                            if isinstance(tc, dict):
                                yield ModelStreamEvent(
                                    tool_call=_normalize_fallback_tool_call(tc),
                                )
                        yield ModelStreamEvent(
                            message_stop=MessageStopInfo(
                                finish_reason=(
                                    response.get("finish_reason")
                                    or response.get("stop_reason")
                                    or "stop"
                                ),
                                usage=response.get("usage", {}) or {},
                                model=response.get("model", "") or final_model,
                                fallback="completion",
                                warning=str(exc),
                            ).to_dict(),
                        )
                        return
                if emitted_visible_content and _is_retryable_stream_error(exc):
                    logger.warning(
                        "call_model_stream_partial_transport_close",
                        error=str(exc),
                        attempt=attempt,
                    )
                    yield ModelStreamEvent(
                        message_stop=MessageStopInfo(
                            finish_reason=final_finish or "stop",
                            usage=final_usage,
                            model=final_model,
                            partial=True,
                            warning=str(exc),
                            resource_exhausted=(
                                final_finish == "insufficient_system_resource"
                            ),
                        ).to_dict(),
                    )
                    return
                logger.warning(
                    "call_model_stream_error",
                    error=str(exc),
                    error_type=type(exc).__name__,
                    error_repr=repr(exc),
                    cause_type=type(exc.__cause__).__name__ if exc.__cause__ else None,
                    cause_repr=repr(exc.__cause__) if exc.__cause__ else None,
                    context_type=type(exc.__context__).__name__ if exc.__context__ else None,
                    context_repr=repr(exc.__context__) if exc.__context__ else None,
                )
                yield ModelStreamEvent(
                    message_stop=MessageStopInfo(
                        finish_reason="error",
                        usage=final_usage,
                        model=final_model,
                        error=str(exc) or repr(exc),
                    ).to_dict(),
                )
                return
            break

        sid = str(tool_use_context.session_id) if tool_use_context.session_id else None
        if not pending_tool_calls and tools and accumulated_content.strip():
            for tc in _try_extract_content_tool_calls(
                accumulated_content,
                known_tool_names=_known_tool_names(tools),
            ):
                yield ModelStreamEvent(tool_call=tc)
        for ev in await _finalize_pending_tool_calls(
            pending_tool_calls, last_delta_emit, sid,
        ):
            yield ev

        yield ModelStreamEvent(
            message_stop=MessageStopInfo(
                finish_reason=final_finish or "stop",
                usage=final_usage,
                model=final_model,
                resource_exhausted=(final_finish == "insufficient_system_resource"),
            ).to_dict(),
        )

    return _call


def production_deps(
    llm: "LLMService",
    *,
    autocompact_token_threshold: int = 0,
    autocompact_keep_recent: int = 0,
    tool_result_budget_chars: int = 0,
) -> QueryDeps:
    """Build the default ``QueryDeps`` bundle.

    Uses ``build_microcompact`` / ``build_autocompact`` from
    :mod:`leagent.memory.compact`` which handle their own internal
    fallback-to-identity when LLM calls fail.

    Callers may pass model-aware overrides for the autocompact threshold,
    keep-recent window, and microcompact budget. Zero values fall back to
    the module defaults.
    """
    from leagent.memory.compact import (
        AUTOCOMPACT_KEEP_RECENT,
        AUTOCOMPACT_TOKEN_THRESHOLD,
        DEFAULT_TOOL_RESULT_BUDGET_CHARS,
        build_autocompact,
        build_microcompact,
    )

    mc_budget = tool_result_budget_chars or DEFAULT_TOOL_RESULT_BUDGET_CHARS
    ac_threshold = autocompact_token_threshold or AUTOCOMPACT_TOKEN_THRESHOLD
    ac_keep = autocompact_keep_recent or AUTOCOMPACT_KEEP_RECENT

    return QueryDeps(
        call_model=_make_llm_call_model(llm),
        microcompact=build_microcompact(llm, budget_chars=mc_budget),
        autocompact=build_autocompact(llm, token_threshold=ac_threshold, keep_recent=ac_keep),
    )
