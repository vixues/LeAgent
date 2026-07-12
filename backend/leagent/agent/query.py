"""Agentic query loop ported from the reference ``query.ts``.

``query()`` is an async generator that owns the think-act-observe loop:

1. Pre-API pipeline: microcompact → progressive transcript compress → autocompact
   → assemble system prompt.
2. Streaming model call via ``deps.call_model`` (emits content deltas and
   coalesced tool calls).
3. Tool orchestration: permission check, concurrent-safe partitioning,
   ``ToolExecutor.run_tool`` dispatch, tool-result messages appended to
   state.
4. Recovery transitions: ``next_turn``, ``max_output_tokens_recovery``,
   ``reactive_compact_retry``, ``token_budget_continuation``.
5. Terminal: ``completed`` / ``max_turns`` / ``aborted_streaming`` /
   ``model_error`` / ``prompt_too_long``.

The loop yields a stream of events (``ModelStreamEvent``, assistant/tool
messages as dicts) and returns a ``Terminal`` via ``StopAsyncIteration.value``.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator

from leagent.agent.deps import ModelStreamEvent, QueryDeps
from leagent.agent.state import AutoCompactTrackingState, QueryState
from leagent.agent.transitions import Continue, ContinueReason, Terminal, TerminalReason
from leagent.config.settings import get_settings
from leagent.context.session_compression import apply_progressive_transcript_compress
from leagent.memory.compact import _approximate_tokens
from leagent.utils.logging import get_logger

if TYPE_CHECKING:
    from leagent.agent.tool_use_context import ToolUseContext

logger = get_logger(__name__)

ASK_USER_TOOL_NAME = "ask_user"
_CANVAS_PUBLISH_TOOL = "canvas_publish"
_COMPACT_INLINE_HTML_BYTES = 20_480
_MIN_SALVAGE_HTML_CHARS = 100
_HTML_COMPLETE_MIN_CHARS = 500
_HTML_BODY_COMPLETE_MIN_CHARS = 2048

_TRUNCATION_RECOVERY_HINT = (
    "[System: your previous output was truncated because "
    "the tool call arguments exceeded the output token "
    "limit. Do NOT retry the same oversized inline call. "
    "For HTML pages: do **not** emit another giant inline `html` string. "
    "Prefer `canvas_publish` with `html_files` (path → source) + "
    "`html_bundle_entry`, or `project_write` shards then `html_files`. "
    "Compact inline `html` is only OK when the full document stays under "
    f"~{_COMPACT_INLINE_HTML_BYTES} bytes. Use short image URLs like "
    "`/api/v1/files/{file_id}/preview` (no JWT tokens in src). "
    "The runtime auto-recovers malformed inline HTML and auto-stages it "
    "as `html_blob_id` when needed — you do **not** need `tool_argument_blob` "
    "for normal webpages. Only use `tool_argument_blob` when a second direct "
    "`canvas_publish` attempt also fails. Prefer plain `chunk` over "
    "`chunk_base64` if blob staging is unavoidable. "
    "For code/project edits: pass `*_blob_id` from `tool_argument_blob` "
    "(`create_and_finalize` with `chunk`).]"
)

_CANVAS_TRUNCATION_INCOMPLETE_HINT = (
    "[System: a truncated `canvas_publish` HTML payload was salvaged and "
    "published so the user can preview partial content. Do **not** regenerate "
    "the whole page from scratch. Continue with `html_files` / `project_write` "
    "shards or a compact patch under "
    f"~{_COMPACT_INLINE_HTML_BYTES} bytes. Prefer short preview URLs.]"
)


@dataclass
class _CanvasLengthSalvage:
    """Result of preparing salvaged ``canvas_publish`` args on length truncation."""

    incomplete: bool
    salvaged_html_bytes: int
    tool_name: str = _CANVAS_PUBLISH_TOOL
    html_closed_by_runtime: bool = False


def _has_truncated_tool_args(tool_calls: list[dict[str, Any]]) -> bool:
    return any(
        isinstance(tc.get("arguments"), dict)
        and isinstance(tc["arguments"].get("__raw__"), str)
        for tc in tool_calls
    )


def _has_canvas_publish_tool(tool_calls: list[dict[str, Any]]) -> bool:
    return any(tc.get("name") == _CANVAS_PUBLISH_TOOL for tc in tool_calls)


def _should_inject_recovery_hint(tool_calls: list[dict[str, Any]]) -> bool:
    """Inject routing hint for raw args or any canvas_publish length truncation."""
    return _has_truncated_tool_args(tool_calls) or _has_canvas_publish_tool(tool_calls)


def _ensure_html_document_closed(html: str) -> tuple[str, bool]:
    """Append missing ``</body></html>`` so truncated salvage still previews."""
    lower = html.lower()
    if "</html>" in lower:
        return html, False
    closed = html.rstrip()
    if "</body>" not in lower:
        closed = f"{closed}\n</body>"
    closed = f"{closed}\n</html>"
    return closed, True


def _is_html_complete_enough(html: str) -> bool:
    body = html.strip()
    if len(body) < _HTML_COMPLETE_MIN_CHARS:
        return False
    lower = body.lower()
    if "</html>" in lower:
        return True
    return len(body) >= _HTML_BODY_COMPLETE_MIN_CHARS and "<body" in lower


def _canvas_args_have_content(args: dict[str, Any]) -> bool:
    html = args.get("html")
    if isinstance(html, str) and html.strip():
        return True
    for key in ("html_blob_id", "html_files_blob_id"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return True
    files = args.get("html_files")
    return isinstance(files, dict) and bool(files)


def _prepare_canvas_length_salvage(
    tool_calls: list[dict[str, Any]],
) -> _CanvasLengthSalvage | None:
    """Mutate salvageable ``canvas_publish`` args in place; return meta or None."""
    from leagent.tools.executor import _recover_canvas_publish_args

    any_salvaged = False
    incomplete = False
    salvaged_bytes = 0
    closed_by_runtime = False

    for tc in tool_calls:
        if tc.get("name") != _CANVAS_PUBLISH_TOOL:
            continue
        args = tc.get("arguments")
        if not isinstance(args, dict):
            continue

        recovered: dict[str, Any] | None = None
        if _canvas_args_have_content(args) and "__raw__" not in args:
            recovered = dict(args)
        elif isinstance(args.get("__raw__"), str):
            recovered = _recover_canvas_publish_args(str(args["__raw__"]))
        if recovered is None or not _canvas_args_have_content(recovered):
            continue

        html = recovered.get("html")
        if isinstance(html, str) and html.strip():
            if len(html.strip()) < _MIN_SALVAGE_HTML_CHARS:
                continue
            was_complete = _is_html_complete_enough(html)
            closed_html, was_closed = _ensure_html_document_closed(html)
            recovered["html"] = closed_html
            salvaged_bytes = max(salvaged_bytes, len(closed_html.encode("utf-8")))
            if was_closed:
                closed_by_runtime = True
            if was_closed or not was_complete:
                incomplete = True
        else:
            # Blob / html_files path — treat as executable without completeness probe.
            salvaged_bytes = max(salvaged_bytes, 0)

        tc["arguments"] = {
            k: v for k, v in recovered.items() if not str(k).startswith("_")
        }
        any_salvaged = True

    if not any_salvaged:
        return None
    return _CanvasLengthSalvage(
        incomplete=incomplete,
        salvaged_html_bytes=salvaged_bytes,
        html_closed_by_runtime=closed_by_runtime,
    )


def _length_recovery_token_override(params: "QueryParams") -> int:
    return min(
        65_536,
        max(16_384, (params.max_output_tokens or 4096) * 4),
    )


def _build_length_recovery_state(
    state: "QueryState",
    params: "QueryParams",
    tool_calls: list[dict[str, Any]],
) -> "QueryState":
    """Build a recovery ``QueryState`` after output-length truncation."""
    recovery_attempt = state.max_output_tokens_recovery_count + 1
    recovery_messages = list(state.messages)
    if _should_inject_recovery_hint(tool_calls):
        recovery_messages.append({
            "role": "user",
            "content": _TRUNCATION_RECOVERY_HINT,
        })
    if recovery_attempt >= 2:
        state.tool_use_context.extra["force_sharded_html"] = True
    return QueryState(
        messages=recovery_messages,
        tool_use_context=state.tool_use_context,
        auto_compact_tracking=state.auto_compact_tracking,
        max_output_tokens_recovery_count=recovery_attempt,
        has_attempted_reactive_compact=state.has_attempted_reactive_compact,
        max_output_tokens_override=_length_recovery_token_override(params),
        turn_count=state.turn_count,
        transition=Continue(reason=ContinueReason.MAX_OUTPUT_TOKENS_RECOVERY),
    )


def _length_recovery_log_extra(
    *,
    state: "QueryState",
    tool_calls: list[dict[str, Any]],
    assistant_text: str,
    executed_vs_regenerated: str,
    salvaged_html_bytes: int = 0,
) -> dict[str, Any]:
    tool_name = next(
        (str(tc.get("name") or "") for tc in tool_calls if tc.get("name")),
        "",
    )
    return {
        "recovery_attempt": state.max_output_tokens_recovery_count + 1,
        "had_tool_calls": bool(tool_calls),
        "had_truncated_tool_args": _has_truncated_tool_args(tool_calls),
        "text_len": len(assistant_text),
        "tool_name": tool_name,
        "salvaged_html_bytes": salvaged_html_bytes,
        "executed_vs_regenerated": executed_vs_regenerated,
    }
# Placeholder tool body so OpenAI-shaped history always has a tool row after ask_user tool_calls.
ASK_USER_PENDING_TOOL_JSON = '{"_wa_pending": true}'

_UI_VARIANTS = frozenset({"questionnaire", "permission"})
_PERMISSION_KINDS = frozenset({"file_access", "tool_run", "mode_change", "generic"})


def _normalize_ask_user_questions(raw: list) -> list[dict[str, Any]]:
    """Best-effort extract of question specs from ask_user tool arguments."""
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        qid = item.get("id")
        prompt = item.get("prompt")
        if not isinstance(qid, str) or not qid.strip():
            continue
        if not isinstance(prompt, str) or not prompt.strip():
            continue
        entry: dict[str, Any] = {
            "id": qid.strip(),
            "prompt": prompt.strip(),
        }
        choices = item.get("choices")
        if isinstance(choices, list):
            entry["choices"] = [str(c) for c in choices if isinstance(c, str) and c.strip()]
        if isinstance(item.get("allow_custom"), bool):
            entry["allow_custom"] = item["allow_custom"]
        if isinstance(item.get("multi_select"), bool):
            entry["multi_select"] = item["multi_select"]

        uv = item.get("ui_variant")
        if isinstance(uv, str) and uv.strip() in _UI_VARIANTS:
            entry["ui_variant"] = uv.strip()

        pk = item.get("permission_kind")
        if isinstance(pk, str) and pk.strip() in _PERMISSION_KINDS:
            entry["permission_kind"] = pk.strip()

        det = item.get("detail")
        if isinstance(det, str) and det.strip():
            entry["detail"] = det.strip()

        pc = item.get("primary_choice")
        if isinstance(pc, str) and pc.strip():
            entry["primary_choice"] = pc.strip()

        sc = item.get("secondary_choice")
        if isinstance(sc, str) and sc.strip():
            entry["secondary_choice"] = sc.strip()

        out.append(entry)
    return out


def _tool_call_id_name_pairs(tool_calls: list[Any]) -> list[tuple[str, str]]:
    """Return ``(id, name)`` for each tool call block (OpenAI wire format)."""
    out: list[tuple[str, str]] = []
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        tid = tc.get("id")
        if not isinstance(tid, str) or not tid.strip():
            continue
        name = tc.get("name")
        fn = tc.get("function")
        if not name and isinstance(fn, dict):
            name = fn.get("name")
        out.append((tid.strip(), str(name or "")))
    return out


def _inject_pending_ask_user_tool_stubs(messages: list[dict[str, Any]]) -> None:
    """Ensure each ``ask_user`` ``tool_call_id`` has a following ``tool`` message.

    Mutates ``messages`` in place. Used before ``call_model`` so providers do not
    return 400 while the UI is still collecting answers.
    """
    idx = 0
    while idx < len(messages):
        msg = messages[idx]
        if msg.get("role") != "assistant":
            idx += 1
            continue
        tcs = msg.get("tool_calls")
        if not isinstance(tcs, list) or not tcs:
            idx += 1
            continue

        ask_ids = [
            tid
            for tid, name in _tool_call_id_name_pairs(tcs)
            if name == ASK_USER_TOOL_NAME
        ]
        if not ask_ids:
            idx += 1
            continue

        end = idx + 1
        while end < len(messages) and messages[end].get("role") == "tool":
            end += 1

        answered: set[str] = set()
        for k in range(idx + 1, end):
            tcid = messages[k].get("tool_call_id")
            if isinstance(tcid, str):
                answered.add(tcid)

        to_insert: list[dict[str, Any]] = []
        for tid in ask_ids:
            if tid not in answered:
                to_insert.append(
                    {
                        "role": "tool",
                        "tool_call_id": tid,
                        "content": ASK_USER_PENDING_TOOL_JSON,
                    },
                )

        for offset, stub in enumerate(to_insert):
            messages.insert(end + offset, stub)

        idx = end + len(to_insert) if to_insert else end


INTERRUPTED_TOOL_RESULT_JSON = json.dumps(
    {
        "_interrupted": True,
        "detail": (
            "No tool result was stored (the run was cancelled or disconnected "
            "before this tool finished)."
        ),
    },
    ensure_ascii=False,
)


def inject_missing_tool_result_stubs(messages: list[dict[str, Any]]) -> None:
    """Ensure every ``tool_calls`` id on an assistant has a following ``tool`` row.

    A user stop can leave ``assistant`` + ``tool_calls`` without matching ``tool``
    messages (the consumer stops mid ``tool_use`` fan-out). OpenAI-compatible APIs
    reject the next request with HTTP 400 until the chain is repaired.

    Runs after :func:`_inject_pending_ask_user_tool_stubs` so ``ask_user`` rows keep
    the pending placeholder instead of the interrupted stub.

    Mutates ``messages`` in place.
    """
    idx = 0
    while idx < len(messages):
        msg = messages[idx]
        if msg.get("role") != "assistant":
            idx += 1
            continue
        tcs = msg.get("tool_calls")
        if not isinstance(tcs, list) or not tcs:
            idx += 1
            continue

        pairs = _tool_call_id_name_pairs(tcs)
        required_ids: list[str] = []
        id_to_name: dict[str, str] = {}
        for tid, nm in pairs:
            if not tid or tid in id_to_name:
                continue
            id_to_name[tid] = nm
            required_ids.append(tid)
        if not required_ids:
            idx += 1
            continue

        end = idx + 1
        while end < len(messages) and messages[end].get("role") == "tool":
            end += 1

        answered: set[str] = set()
        for k in range(idx + 1, end):
            tcid = messages[k].get("tool_call_id")
            if isinstance(tcid, str) and tcid.strip():
                answered.add(tcid.strip())

        missing = [tid for tid in required_ids if tid not in answered]
        if not missing:
            idx = end
            continue

        to_insert: list[dict[str, Any]] = []
        for tid in missing:
            nm = id_to_name.get(tid, "") or ""
            stub: dict[str, Any] = {
                "role": "tool",
                "tool_call_id": tid,
                "content": INTERRUPTED_TOOL_RESULT_JSON,
            }
            if nm:
                stub["name"] = nm
            to_insert.append(stub)

        for offset, stub in enumerate(to_insert):
            messages.insert(end + offset, stub)
        idx = end + len(to_insert)


def _parse_ask_user_tool_call(call: dict[str, Any]) -> list[dict[str, Any]]:
    args = call.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    if not isinstance(args, dict):
        return []
    qs = args.get("questions")
    if not isinstance(qs, list):
        return []
    return _normalize_ask_user_questions(qs)


# ---------------------------------------------------------------------------
# Public params
# ---------------------------------------------------------------------------


@dataclass
class QueryParams:
    """Inputs to ``query()``.

    Mirrors the TS ``QueryParams``:

    - ``messages``: starting conversation history (system prompt is separate).
    - ``system_prompt``: fully-assembled system prompt string. As of the
      prompts-package refactor the caller (typically
      :class:`QueryEngine`) has already folded environment, project
      memory, recall, and session state into this string via
      :class:`PromptBuilder`, so ``query()`` no longer needs the
      structured context maps or the ``<recalled_memory>`` injection.
    - ``tool_use_context``: runtime handle (abort, registry, executor, cache).
    - ``tools_schema``: JSON tool schemas sent to the model.
    - ``max_turns``: guard against runaway loops.
    - ``temperature`` / ``max_output_tokens``: model controls.
      ``model_provider`` / ``model_name`` optionally select a specific model.
    - ``deps``: injected dependencies for streaming + compaction.
    - ``max_tool_calls_per_turn``: cap on parallel tool dispatch (mirrors
      ``AgentConfig.max_tool_calls_per_turn``).
    """

    messages: list[dict[str, Any]]
    system_prompt: str
    tool_use_context: "ToolUseContext"
    deps: QueryDeps

    tools_schema: list[dict[str, Any]] | None = None

    max_turns: int = 15
    max_tool_calls_per_turn: int = 10
    temperature: float | None = None
    max_output_tokens: int | None = None
    max_total_tokens: int | None = None
    model_provider: str | None = None
    model_name: str | None = None
    model_task: str | None = None


# ---------------------------------------------------------------------------
# Yielded event wrappers
# ---------------------------------------------------------------------------


@dataclass
class AssistantMessage:
    """Assistant message yielded between iterations."""

    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    reasoning_content: str = ""

    def to_openai(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.reasoning_content:
            msg["reasoning_content"] = self.reasoning_content
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("arguments", {})),
                    },
                }
                for tc in self.tool_calls
            ]
        return msg


@dataclass
class ToolResultMessage:
    """Tool result appended to history for the next turn."""

    tool_call_id: str
    name: str
    content: str
    success: bool = True
    # Raw tool envelope for ToolResult reconstruction in AgentController.
    envelope: dict[str, Any] | None = None

    def to_openai(self) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "content": self.content,
        }


@dataclass
class SteerMessage:
    """User steer injected mid-turn at a tool-batch boundary.

    History stays append-only: the steer becomes a fresh ``user`` message
    after the current batch's tool results, never a rewrite of anything
    already sent to the model.
    """

    content: str

    def to_openai(self) -> dict[str, Any]:
        return {"role": "user", "content": self.content}


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------


async def query(params: QueryParams) -> AsyncIterator[Any]:
    """Top-level async generator mirroring ``query()`` in ``query.ts``.

    Yields: ``ModelStreamEvent`` (stream deltas), ``AssistantMessage``
    (finalised turn), ``ToolResultMessage`` (observed tool result),
    ``Terminal`` (final frame — always last).
    """
    terminal = None
    try:
        async for item in _query_loop(params):
            if isinstance(item, Terminal):
                terminal = item
                break
            yield item
    finally:
        if terminal is None:
            terminal = Terminal(reason=TerminalReason.COMPLETED)
        yield terminal


async def _query_loop(params: QueryParams) -> AsyncIterator[Any]:
    """Inner loop that rebuilds ``QueryState`` at every ``continue`` site."""
    state = QueryState(
        messages=list(params.messages),
        tool_use_context=params.tool_use_context,
        auto_compact_tracking=AutoCompactTrackingState(),
        turn_count=1,
    )

    while True:
        if state.tool_use_context.aborted:
            yield Terminal(reason=TerminalReason.ABORTED_STREAMING)
            return

        if state.turn_count > params.max_turns:
            yield Terminal(
                reason=TerminalReason.MAX_TURNS,
                meta={"turn_count": state.turn_count - 1},
            )
            return

        # ------------------------------------------------------------------
        # 1) Pre-API pipeline
        # ------------------------------------------------------------------
        messages_for_query = list(state.messages)

        _stage_started = time.perf_counter()
        messages_for_query = await params.deps.microcompact(
            messages_for_query, state.tool_use_context
        )
        try:
            from leagent.utils.metrics import get_metrics

            get_metrics().record_agent_turn_phase(
                "microcompact",
                time.perf_counter() - _stage_started,
            )
        except Exception:
            logger.debug("microcompact_metrics_failed", exc_info=True)

        # Approximate the transcript size once and reuse it to gate the
        # progressive-compress, pre-compact-hook, and autocompact stages.
        # Recomputing it inside each stage was redundant, and below half the
        # autocompact threshold every stage is a no-op — so we skip the
        # (LLM-free but O(transcript)) autocompact scan entirely there.
        try:
            settings = get_settings()
            ac_threshold = settings.session.autocompact_token_threshold
        except Exception:
            settings = None
            ac_threshold = 0
        approx_tokens = _approximate_tokens(messages_for_query)

        if settings is not None and ac_threshold and approx_tokens > ac_threshold * 0.6:
            try:
                _stage_started = time.perf_counter()
                messages_for_query = apply_progressive_transcript_compress(
                    messages_for_query,
                    settings=settings,
                )
                # Content shrank; refresh the estimate for the gates below.
                approx_tokens = _approximate_tokens(messages_for_query)
                try:
                    from leagent.utils.metrics import get_metrics

                    get_metrics().record_agent_turn_phase(
                        "progressive_transcript_compress",
                        time.perf_counter() - _stage_started,
                    )
                except Exception:
                    logger.debug("progressive_transcript_compress_metrics_failed", exc_info=True)
            except Exception:
                logger.exception("progressive_transcript_compress_failed")

        # PreCompact hook (Claude ``PreCompact``): notify observers right
        # before the transcript summarization runs. Gated on the autocompact
        # token threshold so it only fires when a compaction is actually likely.
        _hooks = getattr(state.tool_use_context, "hooks", None)
        if _hooks is not None and approx_tokens > ac_threshold:
            try:
                from uuid import uuid4 as _uuid4

                from leagent.agent.base import AgentContext

                _compact_ctx = AgentContext(
                    session_id=getattr(state.tool_use_context, "session_id", None)
                    or _uuid4(),
                    user_id=getattr(state.tool_use_context, "user_id", None),
                )
                await _hooks.dispatch_pre_compact(_compact_ctx, "autocompact")
            except Exception:
                logger.debug("pre_compact_hook_failed", exc_info=True)

        # The system prompt arrives fully-assembled from the prompt
        # builder (L0..L7). Autocompact still uses it as a size anchor
        # but we no longer fold environment / recall into it here —
        # recall is rendered into the system prompt at L5.
        full_system_prompt = params.system_prompt
        # Autocompact returns the transcript unchanged well below its threshold;
        # skip the scan there. Always run it when the threshold is unknown/zero.
        if (not ac_threshold) or approx_tokens > ac_threshold * 0.5:
            _stage_started = time.perf_counter()
            messages_for_query = await params.deps.autocompact(
                messages_for_query, state.tool_use_context, full_system_prompt
            )
            try:
                from leagent.utils.metrics import get_metrics

                get_metrics().record_agent_turn_phase(
                    "autocompact",
                    time.perf_counter() - _stage_started,
                )
            except Exception:
                logger.debug("autocompact_metrics_failed", exc_info=True)

        # Drop orphan tool rows at the head (e.g. corrupted session or a prior
        # compaction bug). OpenAI rejects ``tool`` without a preceding assistant
        # ``tool_calls`` block.
        while messages_for_query and messages_for_query[0].get("role") == "tool":
            messages_for_query.pop(0)

        _inject_pending_ask_user_tool_stubs(messages_for_query)
        inject_missing_tool_result_stubs(messages_for_query)

        # ------------------------------------------------------------------
        # 2) Stream model response
        # ------------------------------------------------------------------
        assistant_content_parts: list[str] = []
        assistant_reasoning_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        stream_error: dict[str, Any] | None = None
        finish_reason = "stop"
        usage: dict[str, Any] = {}
        model_name = ""

        try:
            call_kwargs: dict[str, Any] = {
                "messages": messages_for_query,
                "system_prompt": full_system_prompt,
                "tools": params.tools_schema,
                "tool_use_context": state.tool_use_context,
                "temperature": params.temperature,
                "max_output_tokens": (
                    state.max_output_tokens_override or params.max_output_tokens
                ),
            }
            if params.model_provider:
                call_kwargs["model_provider"] = params.model_provider
            if params.model_name:
                call_kwargs["model_name"] = params.model_name
            if params.model_task:
                call_kwargs["model_task"] = params.model_task
            stream = params.deps.call_model(
                **call_kwargs,
            )
            async for event in stream:
                if state.tool_use_context.aborted:
                    yield Terminal(reason=TerminalReason.ABORTED_STREAMING)
                    return

                yield event  # surface the raw stream event to SDK callers

                if event.content_delta:
                    assistant_content_parts.append(event.content_delta)
                if event.reasoning_delta:
                    assistant_reasoning_parts.append(event.reasoning_delta)
                if event.tool_call:
                    tool_calls.append(event.tool_call)
                if event.message_stop:
                    finish_reason = event.message_stop.get("finish_reason", "stop")
                    usage = event.message_stop.get("usage", {}) or {}
                    model_name = event.message_stop.get("model", "")
                    if "error" in event.message_stop:
                        stream_error = event.message_stop
        except asyncio.CancelledError:
            yield Terminal(reason=TerminalReason.ABORTED_STREAMING)
            return
        except Exception as exc:  # noqa: BLE001
            err_str = str(exc).lower()
            is_context_overflow = (
                "context_length" in err_str
                or "context length" in err_str
                or "maximum context" in err_str
                or "reduce your prompt" in err_str
                or "prompt is too long" in err_str
            )
            if is_context_overflow:
                logger.warning(
                    "query_loop_prompt_too_long",
                    extra={"error": str(exc)},
                )
                yield Terminal(
                    reason=TerminalReason.PROMPT_TOO_LONG,
                    meta={"error": str(exc)},
                )
            else:
                logger.warning("query_loop_model_error", extra={"error": str(exc)})
                yield Terminal(
                    reason=TerminalReason.MODEL_ERROR,
                    meta={"error": str(exc)},
                )
            return

        # ------------------------------------------------------------------
        # 3) Build assistant message, handle errors / recovery
        # ------------------------------------------------------------------
        from leagent.services.session.artifacts import (
            collect_image_preview_urls_from_messages,
            rewrite_inline_data_image_markdown,
        )

        assistant_text = rewrite_inline_data_image_markdown(
            "".join(assistant_content_parts),
            collect_image_preview_urls_from_messages(state.messages),
        )
        ask_user_calls = [tc for tc in tool_calls if tc.get("name") == ASK_USER_TOOL_NAME]
        non_ask_user = [tc for tc in tool_calls if tc.get("name") != ASK_USER_TOOL_NAME]
        effective_tool_calls = tool_calls
        if ask_user_calls:
            if non_ask_user:
                logger.warning(
                    "query_loop_dropping_non_ask_user_tools",
                    extra={"dropped": [tc.get("name") for tc in non_ask_user]},
                )
            if len(ask_user_calls) > 1:
                logger.warning(
                    "query_loop_multiple_ask_user_using_first_only",
                    extra={"count": len(ask_user_calls)},
                )
            effective_tool_calls = ask_user_calls[:1]

        assistant_msg = AssistantMessage(
            content=assistant_text,
            tool_calls=effective_tool_calls,
            usage=usage,
            model=model_name,
            reasoning_content="".join(assistant_reasoning_parts),
        )
        yield assistant_msg

        # Track total usage on the context for the owning QueryEngine.
        tracking = state.tool_use_context.query_tracking
        if usage:
            agg = tracking.setdefault(
                "usage",
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )
            agg["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
            agg["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
            agg["total_tokens"] += int(usage.get("total_tokens", 0) or 0)

        if params.max_total_tokens and params.max_total_tokens > 0:
            total_so_far = int(
                tracking.get("usage", {}).get("total_tokens", 0) or 0
            )
            if total_so_far >= params.max_total_tokens:
                logger.warning(
                    "query_loop_token_budget_exceeded",
                    extra={
                        "total_tokens": total_so_far,
                        "budget": params.max_total_tokens,
                    },
                )
                yield Terminal(
                    reason=TerminalReason.TOKEN_BUDGET_EXCEEDED,
                    meta={
                        "turn_count": state.turn_count,
                        "usage": tracking.get("usage", {}),
                        "budget": params.max_total_tokens,
                    },
                )
                return

        canvas_length_salvage: _CanvasLengthSalvage | None = None

        def _try_length_regenerate() -> bool:
            """Return True if the loop should ``continue`` with a regenerate recovery.

            When ``canvas_publish`` args are salvageable, mutate them in place and
            fall through to tool dispatch instead of discarding the generation.
            """
            nonlocal canvas_length_salvage, state
            salvage = _prepare_canvas_length_salvage(effective_tool_calls)
            if salvage is not None:
                canvas_length_salvage = salvage
                # Keep assistant_msg tool_calls in sync (same list refs when possible).
                assistant_msg.tool_calls = effective_tool_calls
                logger.info(
                    "query_loop_length_truncation_recovery",
                    extra=_length_recovery_log_extra(
                        state=state,
                        tool_calls=effective_tool_calls,
                        assistant_text=assistant_text,
                        executed_vs_regenerated="executed",
                        salvaged_html_bytes=salvage.salvaged_html_bytes,
                    ),
                )
                return False
            logger.info(
                "query_loop_length_truncation_recovery",
                extra=_length_recovery_log_extra(
                    state=state,
                    tool_calls=tool_calls,
                    assistant_text=assistant_text,
                    executed_vs_regenerated="regenerated",
                ),
            )
            state = _build_length_recovery_state(state, params, tool_calls)
            return True

        if stream_error is not None:
            err_kind = str(stream_error.get("error", "")).lower()
            if (
                "max_output" in err_kind or finish_reason == "length"
            ) and state.max_output_tokens_recovery_count < 2:
                if _try_length_regenerate():
                    continue
            else:
                yield Terminal(
                    reason=TerminalReason.MODEL_ERROR,
                    meta={"error": str(stream_error)},
                )
                return

        # Recover from output-length truncation even when the provider
        # does not surface an explicit error (e.g. DeepSeek returns
        # finish_reason="length" without an error payload).  Without this
        # check the truncated response — which usually has no complete
        # tool calls — falls through to the "no tool calls → completed"
        # branch and silently terminates the agent mid-answer.
        # Salvageable canvas_publish falls through to tool dispatch above.
        if (
            canvas_length_salvage is None
            and finish_reason == "length"
            and state.max_output_tokens_recovery_count < 2
        ):
            if _try_length_regenerate():
                continue

        if state.max_output_tokens_recovery_count >= 2:
            state.tool_use_context.extra["force_sharded_html"] = True

        # ------------------------------------------------------------------
        # 3b) Exhausted output-length recovery: emit a user-visible error
        #     instead of silently completing with no output.
        # ------------------------------------------------------------------
        if (
            finish_reason == "length"
            and state.max_output_tokens_recovery_count >= 2
            and not assistant_msg.tool_calls
        ):
            logger.warning(
                "query_loop_length_recovery_exhausted",
                extra={
                    "recovery_count": state.max_output_tokens_recovery_count,
                    "text_len": len(assistant_text),
                },
            )
            fallback_text = (
                assistant_text
                + "\n\n"
                + "[The response was interrupted because the generated "
                "content exceeded the maximum output length. Please try "
                "a simpler request, or ask me to break the task into "
                "smaller steps.]"
            ) if assistant_text.strip() else (
                "[The response could not be completed because the "
                "generated content exceeded the maximum output length "
                "after multiple attempts. Please try a simpler request, "
                "or ask me to break the task into smaller steps.]"
            )
            yield AssistantMessage(
                content=fallback_text,
                tool_calls=[],
                usage=usage,
                model=model_name,
            )
            yield Terminal(
                reason=TerminalReason.COMPLETED,
                meta={
                    "turn_count": state.turn_count,
                    "usage": tracking.get("usage", {}),
                    "truncation_exhausted": True,
                },
            )
            return

        # Persist the assistant turn into history before any follow-up.
        new_messages = [*state.messages, assistant_msg.to_openai()]

        # ------------------------------------------------------------------
        # 4) Terminal: no tool calls -> we're done
        # ------------------------------------------------------------------
        if not assistant_msg.tool_calls:
            yield Terminal(
                reason=TerminalReason.COMPLETED,
                meta={
                    "turn_count": state.turn_count,
                    "usage": tracking.get("usage", {}),
                },
            )
            return

        # ------------------------------------------------------------------
        # 4b) ask_user: exit without dispatch; client supplies tool results later
        # ------------------------------------------------------------------
        if ask_user_calls:
            primary = effective_tool_calls[0]
            questions = _parse_ask_user_tool_call(primary)
            yield Terminal(
                reason=TerminalReason.AWAITING_USER_INPUT,
                meta={
                    "turn_count": state.turn_count,
                    "usage": tracking.get("usage", {}),
                    "tool_call": {
                        "id": primary.get("id"),
                        "name": primary.get("name"),
                        "arguments": primary.get("arguments") or {},
                    },
                    "questions": questions,
                },
            )
            return

        # ------------------------------------------------------------------
        # 4c) Approval gate: pause instead of fail-closed (Codex-style)
        # ------------------------------------------------------------------
        capped = effective_tool_calls[: params.max_tool_calls_per_turn]
        approval_terminal = await _approval_pause_terminal(
            capped, state.tool_use_context,
            turn_count=state.turn_count,
            usage=tracking.get("usage", {}),
        )
        if approval_terminal is not None:
            yield approval_terminal
            return

        # ------------------------------------------------------------------
        # 5) Tool orchestration
        # ------------------------------------------------------------------
        tool_results = await _dispatch_tools(capped, state.tool_use_context)
        for tr in tool_results:
            yield tr
            new_messages.append(tr.to_openai())

        # ------------------------------------------------------------------
        # 5b) Steer injection: drain pending mid-turn user messages at the
        #     tool-batch boundary (append-only; Codex-style steering)
        # ------------------------------------------------------------------
        for steer in _drain_steer_messages(state.tool_use_context):
            yield steer
            new_messages.append(steer.to_openai())

        # ------------------------------------------------------------------
        # 6) Next turn
        # ------------------------------------------------------------------
        if canvas_length_salvage is not None and canvas_length_salvage.incomplete:
            new_messages.append({
                "role": "user",
                "content": _CANVAS_TRUNCATION_INCOMPLETE_HINT,
            })
            state = QueryState(
                messages=new_messages,
                tool_use_context=state.tool_use_context,
                auto_compact_tracking=state.auto_compact_tracking,
                max_output_tokens_recovery_count=max(
                    1, state.max_output_tokens_recovery_count
                ),
                has_attempted_reactive_compact=False,
                max_output_tokens_override=_length_recovery_token_override(params),
                turn_count=state.turn_count + 1,
                transition=Continue(reason=ContinueReason.NEXT_TURN),
            )
        else:
            state = QueryState(
                messages=new_messages,
                tool_use_context=state.tool_use_context,
                auto_compact_tracking=state.auto_compact_tracking,
                max_output_tokens_recovery_count=0,
                has_attempted_reactive_compact=False,
                max_output_tokens_override=None,
                turn_count=state.turn_count + 1,
                transition=Continue(reason=ContinueReason.NEXT_TURN),
            )


# ---------------------------------------------------------------------------
# Steer helper
# ---------------------------------------------------------------------------


def _drain_steer_messages(ctx: "ToolUseContext") -> list[SteerMessage]:
    """Collect pending steer messages for this session (may be empty)."""
    session_id = getattr(ctx, "session_id", None)
    if session_id is None:
        return []
    try:
        from leagent.agent.control import get_session_control_registry

        texts = get_session_control_registry().drain_steer(str(session_id))
    except Exception:  # noqa: BLE001
        logger.warning("steer_drain_failed", exc_info=True)
        return []
    if texts:
        logger.info(
            "steer_injected",
            extra={"session_id": str(session_id), "count": len(texts)},
        )
    return [SteerMessage(content=t) for t in texts]


# ---------------------------------------------------------------------------
# Approval gate helper
# ---------------------------------------------------------------------------


async def _auto_review_resolved(
    pending: Any,
    args: dict[str, Any],
    ctx: "ToolUseContext",
) -> bool:
    """Triage a pending approval with the auto-review reviewer.

    Returns ``True`` when the request was resolved without the human
    (allow → one-shot grant recorded; deny → fail-closed denial stands)
    and ``False`` to escalate to the user's approval card.
    """
    session_id = getattr(ctx, "session_id", None)
    if session_id is None:
        return False
    try:
        from leagent.tools.approval import get_approval_store

        store = get_approval_store()
        if store.get_reviewer(str(session_id)) != "auto_review":
            return False

        from leagent.tools.auto_review import auto_review_decision

        sm = getattr(getattr(ctx, "executor", None), "_service_manager", None)
        decision, rationale = await auto_review_decision(
            pending, args, service_manager=sm,
        )
    except Exception:  # noqa: BLE001
        logger.warning("auto_review_failed", exc_info=True)
        return False

    if decision == "escalate":
        return False

    if decision == "allow":
        store.grant(str(session_id), pending.tool_name, scope="once")

    try:
        from leagent.api.v1.chat.approvals import audit_approval_decision

        await audit_approval_decision(
            session_id=session_id,
            user_id=getattr(ctx, "user_id", None),
            pending=pending,
            decision="allow_once" if decision == "allow" else "deny",
            decided_by="auto_review",
        )
    except Exception:  # noqa: BLE001
        logger.warning("auto_review_audit_failed", exc_info=True)

    logger.info(
        "auto_review_resolved",
        extra={
            "tool": pending.tool_name,
            "decision": decision,
            "rationale": rationale[:200],
        },
    )
    return True


async def _approval_pause_terminal(
    tool_calls: list[dict[str, Any]],
    ctx: "ToolUseContext",
    *,
    turn_count: int,
    usage: dict[str, Any],
) -> Terminal | None:
    """Return an ``AWAITING_USER_INPUT`` terminal if a call needs approval.

    Instead of dispatching a gated tool (which would fail closed), the
    turn pauses with a synthesized permission question. The kernel saves
    a checkpoint; the user's Allow/Deny comes back via ``tool_replies``
    and (on allow) records a grant so the re-issued call passes.

    When the session's ``approvals_reviewer`` is ``auto_review``, a cheap
    reviewer model triages the request first: ``allow`` grants the call
    once (no pause), ``deny`` leaves the fail-closed denial in place, and
    ``escalate`` falls through to the human approval card.
    """
    executor = getattr(ctx, "executor", None)
    if executor is None or not hasattr(executor, "approval_requirement"):
        return None

    for call in tool_calls:
        name = call.get("name") or ""
        args = call.get("arguments") or {}
        if not isinstance(args, dict):
            args = {}
        try:
            pending = executor.approval_requirement(name, args, ctx)
        except Exception:  # noqa: BLE001
            logger.warning("approval_precheck_failed", extra={"tool": name}, exc_info=True)
            continue
        if pending is None:
            continue

        call_id = str(call.get("id") or "")
        pending.tool_call_id = call_id

        if await _auto_review_resolved(pending, args, ctx):
            continue
        try:
            from leagent.tools.approval import build_approval_question, get_approval_store

            if ctx.session_id is not None:
                get_approval_store().set_pending(str(ctx.session_id), pending)
            question = build_approval_question(
                tool_call_id=call_id,
                tool_name=name,
                reason=pending.reason,
                detail=pending.detail,
            )
        except Exception:  # noqa: BLE001
            logger.warning("approval_pause_setup_failed", exc_info=True)
            continue

        logger.info(
            "approval_pause",
            extra={"tool": name, "call_id": call_id, "reason": pending.reason},
        )
        return Terminal(
            reason=TerminalReason.AWAITING_USER_INPUT,
            meta={
                "turn_count": turn_count,
                "usage": usage,
                "tool_call": {
                    "id": call_id,
                    "name": name,
                    "arguments": args,
                },
                "questions": [question],
                "approval_request": pending.to_meta(),
            },
        )
    return None


# ---------------------------------------------------------------------------
# Tool dispatch helper
# ---------------------------------------------------------------------------


def _tool_envelope_from_base(base: Any) -> dict[str, Any]:
    return {
        "success": bool(getattr(base, "success", True)),
        "data": getattr(base, "data", None),
        "error": getattr(base, "error", None),
        "metadata": dict(getattr(base, "metadata", None) or {}),
        "duration_ms": int(getattr(base, "duration_ms", 0) or 0),
    }


async def _dispatch_tools(
    tool_calls: list[dict[str, Any]],
    ctx: "ToolUseContext",
) -> list[ToolResultMessage]:
    """Run the LLM's requested tool calls through the executor.

    Concurrency rule: tools advertising ``is_concurrency_safe = True`` run in
    parallel; everything else runs sequentially, matching the reference
    partitioning behaviour.
    """
    if not tool_calls:
        return []

    concurrent: list[dict[str, Any]] = []
    serial: list[dict[str, Any]] = []
    for tc in tool_calls:
        tool = ctx.tools.find_by_name(tc["name"]) if ctx.tools else None
        if tool is not None and getattr(tool, "is_concurrency_safe", False):
            concurrent.append(tc)
        else:
            serial.append(tc)

    results: list[ToolResultMessage] = []
    from leagent.agent.recovery import ErrorRecovery

    recovery = ErrorRecovery(ctx.executor)

    async def _run_one(call: dict[str, Any]) -> ToolResultMessage:
        name = call["name"]
        args = call.get("arguments") or {}
        if ctx.aborted:
            return ToolResultMessage(
                tool_call_id=call["id"],
                name=name,
                content="Aborted before execution",
                success=False,
                envelope=None,
            )
        if isinstance(args, dict) and isinstance(args.get("__raw__"), str):
            logger.info(
                "tool_dispatch_raw_args_detected",
                extra={"tool": name, "call_id": call.get("id")},
            )
        try:
            from leagent.agent.base import ToolCall

            cid = call.get("id")
            tool_call = ToolCall(
                id=str(cid) if cid is not None else "",
                name=name,
                arguments=args if isinstance(args, dict) else {},
            )
            base = await recovery.as_middleware()(tool_call, ctx)
            content = _serialize_result(base)
            err_text = str(getattr(base, "error", "") or "")
            if not getattr(base, "success", True) and (
                "Malformed tool arguments JSON" in err_text
                or "`code_execution` did not run:" in err_text
            ):
                logger.warning(
                    "tool_dispatch_raw_args_unrecoverable",
                    extra={
                        "tool": name,
                        "call_id": call.get("id"),
                        "tool_arguments_json_unrecoverable": True,
                    },
                )
            return ToolResultMessage(
                tool_call_id=call["id"],
                name=name,
                content=content,
                success=getattr(base, "success", True),
                envelope=_tool_envelope_from_base(base),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("tool_dispatch_failed", extra={"tool": name, "error": str(exc)})
            return ToolResultMessage(
                tool_call_id=call["id"],
                name=name,
                content=f"Error: {exc}",
                success=False,
                envelope=None,
            )

    if concurrent:
        results.extend(
            await asyncio.gather(*[_run_one(tc) for tc in concurrent])
        )
    for tc in serial:
        results.append(await _run_one(tc))
    # Preserve original call order (OpenAI tool-result API requires matching IDs).
    by_id = {r.tool_call_id: r for r in results}
    return [by_id[tc["id"]] for tc in tool_calls if tc["id"] in by_id]


def _serialize_result(result: Any) -> str:
    """Flatten a ``ToolResult`` envelope into the string the LLM consumes."""
    success = bool(getattr(result, "success", True))
    data = getattr(result, "data", result)
    error = getattr(result, "error", None)
    if not success:
        if isinstance(data, dict) and data:
            payload = {
                "tool_ok": False,
                "error": error or "Unknown error",
                "detail": data,
            }
            try:
                return json.dumps(payload, ensure_ascii=False, default=str)
            except TypeError:
                pass
        return f"Error: {error or 'Unknown error'}"
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except TypeError:
        return str(data)
