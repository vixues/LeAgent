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
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator

from leagent.agent.deps import ModelStreamEvent, QueryDeps
from leagent.agent.state import AutoCompactTrackingState, QueryState
from leagent.agent.transitions import Continue, ContinueReason, Terminal, TerminalReason
from leagent.config.settings import get_settings
from leagent.context.session_compression import apply_progressive_transcript_compress
from leagent.memory.compact import _approximate_tokens

if TYPE_CHECKING:
    from leagent.agent.tool_use_context import ToolUseContext

logger = logging.getLogger(__name__)

ASK_USER_TOOL_NAME = "ask_user"
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
    - ``temperature`` / ``max_output_tokens`` / ``model_tier``: model controls.
      ``model_provider`` / ``model_name`` optionally bypass tier routing.
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
    model_tier: str = "tier1"
    model_provider: str | None = None
    model_name: str | None = None


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

        try:
            settings = get_settings()
            approx_tokens = _approximate_tokens(messages_for_query)
            compress_threshold = settings.session.autocompact_token_threshold * 0.6
            if approx_tokens > compress_threshold:
                _stage_started = time.perf_counter()
                messages_for_query = apply_progressive_transcript_compress(
                    messages_for_query,
                    settings=settings,
                )
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

        # The system prompt arrives fully-assembled from the prompt
        # builder (L0..L7). Autocompact still uses it as a size anchor
        # but we no longer fold environment / recall into it here —
        # recall is rendered into the system prompt at L5.
        full_system_prompt = params.system_prompt
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
                "model_tier": params.model_tier,
            }
            if params.model_provider:
                call_kwargs["model_provider"] = params.model_provider
            if params.model_name:
                call_kwargs["model_name"] = params.model_name
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
            logger.warning("query_loop_model_error", extra={"error": str(exc)})
            yield Terminal(
                reason=TerminalReason.MODEL_ERROR,
                meta={"error": str(exc)},
            )
            return

        # ------------------------------------------------------------------
        # 3) Build assistant message, handle errors / recovery
        # ------------------------------------------------------------------
        assistant_text = "".join(assistant_content_parts)
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

        if stream_error is not None:
            err_kind = str(stream_error.get("error", "")).lower()
            if (
                "max_output" in err_kind or finish_reason == "length"
            ) and state.max_output_tokens_recovery_count < 2:
                had_truncated = any(
                    isinstance(tc.get("arguments"), dict)
                    and isinstance(tc["arguments"].get("__raw__"), str)
                    for tc in tool_calls
                )
                recovery_messages = list(state.messages)
                if had_truncated:
                    recovery_messages.append({
                        "role": "user",
                        "content": (
                            "[System: your previous output was truncated because "
                            "the tool call arguments exceeded the output token "
                            "limit. Do NOT retry the same oversized inline call. "
                            "If the full payload fits in one chunk (under ~64K "
                            "UTF-8 chars): use `tool_argument_blob` with "
                            "`action=create_and_finalize` and `chunk` or "
                            "`chunk_base64`, then pass `*_blob_id` to the "
                            "consumer tool. Use multi-step "
                            "`create` → `append` → `finalize` only when the "
                            "payload was cut mid-stream and needs more appends.]"
                        ),
                    })
                state = QueryState(
                    messages=recovery_messages,
                    tool_use_context=state.tool_use_context,
                    auto_compact_tracking=state.auto_compact_tracking,
                    max_output_tokens_recovery_count=state.max_output_tokens_recovery_count
                    + 1,
                    has_attempted_reactive_compact=state.has_attempted_reactive_compact,
                    max_output_tokens_override=(params.max_output_tokens or 4096) * 2,
                    turn_count=state.turn_count,
                    transition=Continue(reason=ContinueReason.MAX_OUTPUT_TOKENS_RECOVERY),
                )
                continue
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
        if (
            finish_reason == "length"
            and state.max_output_tokens_recovery_count < 2
        ):
            had_truncated_tool_args = any(
                isinstance(tc.get("arguments"), dict)
                and isinstance(tc["arguments"].get("__raw__"), str)
                for tc in tool_calls
            )
            recovery_attempt = state.max_output_tokens_recovery_count + 1
            logger.info(
                "query_loop_length_truncation_recovery",
                extra={
                    "recovery_attempt": recovery_attempt,
                    "had_tool_calls": bool(assistant_msg.tool_calls),
                    "had_truncated_tool_args": had_truncated_tool_args,
                    "text_len": len(assistant_text),
                },
            )
            recovery_messages = list(state.messages)
            if had_truncated_tool_args:
                recovery_messages.append({
                    "role": "user",
                    "content": (
                        "[System: your previous output was truncated because "
                        "the tool call arguments exceeded the output token "
                        "limit. Do NOT retry the same oversized inline call. "
                        "For HTML pages or long code: if the full body fits one "
                        "chunk (under ~64K UTF-8 chars), use "
                        "`tool_argument_blob` with `action=create_and_finalize` "
                        "then `canvas_publish(html_blob_id=…)` or "
                        "`code_execution(source_blob_id=…)`. Use "
                        "`create` → `append` → `finalize` only when output was "
                        "cut mid-payload and needs additional appends.]"
                    ),
                })
            state = QueryState(
                messages=recovery_messages,
                tool_use_context=state.tool_use_context,
                auto_compact_tracking=state.auto_compact_tracking,
                max_output_tokens_recovery_count=recovery_attempt,
                has_attempted_reactive_compact=state.has_attempted_reactive_compact,
                max_output_tokens_override=(params.max_output_tokens or 4096) * 2,
                turn_count=state.turn_count,
                transition=Continue(reason=ContinueReason.MAX_OUTPUT_TOKENS_RECOVERY),
            )
            continue

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
        # 5) Tool orchestration
        # ------------------------------------------------------------------
        capped = effective_tool_calls[: params.max_tool_calls_per_turn]
        tool_results = await _dispatch_tools(capped, state.tool_use_context)
        for tr in tool_results:
            yield tr
            new_messages.append(tr.to_openai())

        # ------------------------------------------------------------------
        # 6) Next turn
        # ------------------------------------------------------------------
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
