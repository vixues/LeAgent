"""Dependency-injection container for ``query()``.

Mirrors ``./query/deps.ts``: exposes the external effects the query loop
needs (model streaming + compaction hooks) behind a Protocol so tests can
inject a fake model without monkey-patching ``LLMService``.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
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


def _partial_arguments_dict(raw: str) -> dict[str, Any] | None:
    """Return parsed tool args when ``raw`` is complete JSON; else None."""
    parsed = parse_tool_arguments_str(raw)
    return parsed if isinstance(parsed, dict) else None


async def _try_blob_streaming_ingest(
    tool_name: str, raw_args: str,
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

    import base64 as _b64
    import binascii as _binascii

    b64_str = recovered.get("chunk_base64", "")
    if not b64_str:
        return None

    def _decode_b64_tolerant(raw: str) -> str | None:
        """Decode base64, trimming trailing incomplete groups if truncated."""
        stripped = raw.strip()
        if not stripped:
            return None
        try:
            return _b64.b64decode(stripped, validate=True).decode("utf-8")
        except (_binascii.Error, ValueError, UnicodeDecodeError):
            pass
        # Truncated output: trim to the nearest multiple-of-4 boundary
        trimmed = stripped[: len(stripped) - (len(stripped) % 4)]
        if len(trimmed) < 4:
            return None
        try:
            return _b64.b64decode(trimmed, validate=True).decode("utf-8")
        except (_binascii.Error, ValueError, UnicodeDecodeError):
            # Last resort: non-strict decode (ignores whitespace / bad chars)
            try:
                return _b64.b64decode(trimmed).decode("utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                return None

    chunk_text = _decode_b64_tolerant(b64_str)
    if chunk_text is None:
        return None

    action = recovered.get("action", "append")
    blob_id = recovered.get("blob_id", "")

    from leagent.tools.util.tool_argument_blob import ToolArgumentBlobStore

    ingest_sid = "__streaming_ingest__"
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
        model_tier: str = "tier1",
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


async def _identity_microcompact(
    messages: list[dict[str, Any]],
    tool_use_context: "ToolUseContext",
) -> list[dict[str, Any]]:
    return messages


async def _identity_autocompact(
    messages: list[dict[str, Any]],
    tool_use_context: "ToolUseContext",
    system_prompt: str,
) -> list[dict[str, Any]]:
    return messages


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
        model_tier: str = "tier1",
        model_provider: str | None = None,
        model_name: str | None = None,
    ) -> AsyncIterator[ModelStreamEvent]:
        full_messages: list[dict[str, Any]] = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

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

            try:
                stream_kw: dict[str, Any] = {}
                if max_output_tokens is not None:
                    stream_kw["max_tokens"] = max_output_tokens
                if model_provider:
                    stream_kw["provider"] = model_provider
                if model_name:
                    stream_kw["model"] = model_name
                async for chunk in llm.chat_stream(
                    messages=full_messages,
                    tools=tools,
                    tool_choice="auto" if tools else None,
                    temperature=temperature,
                    model_tier=model_tier,
                    **stream_kw,
                ):
                    reasoning_piece: str | None = None
                    if chunk.raw_delta and isinstance(chunk.raw_delta.get("reasoning_content"), str):
                        reasoning_piece = chunk.raw_delta["reasoning_content"]
                    if chunk.content or reasoning_piece:
                        if chunk.content:
                            emitted_visible_content = True
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
                        if fargs := fn.get("arguments"):
                            slot["arguments"] += fargs

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
                    await asyncio.sleep(0.5)
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
                            model_tier=model_tier,
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
                                yield ModelStreamEvent(tool_call=tc)
                        yield ModelStreamEvent(
                            message_stop={
                                "finish_reason": response.get("finish_reason")
                                or response.get("stop_reason")
                                or "stop",
                                "usage": response.get("usage", {}) or {},
                                "model": response.get("model", "") or final_model,
                                "fallback": "completion",
                                "warning": str(exc),
                            },
                        )
                        return
                if emitted_visible_content and _is_retryable_stream_error(exc):
                    logger.warning(
                        "call_model_stream_partial_transport_close",
                        error=str(exc),
                        attempt=attempt,
                    )
                    _partial_stop: dict[str, Any] = {
                        "finish_reason": final_finish or "stop",
                        "usage": final_usage,
                        "model": final_model,
                        "partial": True,
                        "warning": str(exc),
                    }
                    if final_finish == "insufficient_system_resource":
                        _partial_stop["resource_exhausted"] = True
                    yield ModelStreamEvent(message_stop=_partial_stop)
                    return
                # Some transport/TLS errors can have an empty str(); include the type and repr
                # so operators can diagnose proxy/DNS/TLS issues from logs.
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
                    message_stop={
                        "finish_reason": "error",
                        "usage": final_usage,
                        "model": final_model,
                        "error": str(exc) or repr(exc),
                    },
                )
                return
            break

        for idx in sorted(pending_tool_calls.keys()):
            slot = pending_tool_calls[idx]
            args_str = slot.get("arguments")
            if not isinstance(args_str, str) or not args_str:
                continue
            rec = last_delta_emit.get(idx)
            if rec is not None and int(rec.get("sent_len", 0)) >= len(args_str):
                continue
            yield ModelStreamEvent(
                tool_call_delta=_tool_call_delta_payload(idx, slot),
            )
            _record_tool_delta_emit(idx, len(args_str), last_delta_emit)

        for slot in sorted(pending_tool_calls.keys()):
            tc = pending_tool_calls[slot]
            args_str = tc.get("arguments") or "{}"
            if isinstance(args_str, dict):
                args = args_str
            elif isinstance(args_str, str):
                parsed = parse_tool_arguments_str(args_str)
                if parsed is not None:
                    args = parsed
                else:
                    ingested = await _try_blob_streaming_ingest(
                        tc.get("name", ""), args_str,
                    )
                    if ingested is not None:
                        args = ingested
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
                            tool_call_index=slot,
                        )
                        args = {"__raw__": args_str}
            else:
                args = {}
            yield ModelStreamEvent(
                tool_call={
                    "id": tc["id"] or f"call_{slot}",
                    "name": tc["name"],
                    "arguments": args,
                },
            )

        _final_stop: dict[str, Any] = {
            "finish_reason": final_finish or "stop",
            "usage": final_usage,
            "model": final_model,
        }
        if final_finish == "insufficient_system_resource":
            _final_stop["resource_exhausted"] = True
        yield ModelStreamEvent(message_stop=_final_stop)

    return _call


def production_deps(llm: "LLMService") -> QueryDeps:
    """Build the default ``QueryDeps`` bundle.

    ``microcompact``/``autocompact`` fall back to identity so the loop runs
    even before ``memory.compact`` is configured; the memory module replaces
    these when compaction is requested.
    """
    from leagent.memory.compact import build_autocompact, build_microcompact

    return QueryDeps(
        call_model=_make_llm_call_model(llm),
        microcompact=build_microcompact(llm),
        autocompact=build_autocompact(llm),
    )
