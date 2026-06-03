"""Sub-agent forking built on top of :class:`QueryEngine.fork`.

The reference architecture exposes sub-agent delegation via two vehicles:

* :class:`ScriptAgentTool` (``agent/script_agent.py``) — a specialised
  Excel/Python analyst.
* :class:`AgentTool` (this module) — a general-purpose sub-agent the
  parent LLM can invoke for any subtask.

Both lean on the same primitive: :meth:`QueryEngine.fork` plus a
child-scoped :class:`~leagent.tools.executor.ToolExecutor` (see
:func:`fork_scoped_engine`) so tool lookup matches the LLM's filtered
registry. The child shares the parent's file-state cache while starting
with a fresh conversation history, and can inherit the parent's abort
event so cancellation propagates.

:func:`fork_subagent` is the single entrypoint. It accepts either a
parent :class:`AgentController` or a parent :class:`QueryEngine`; the
former is unwrapped to its owned ``QueryEngine`` where possible. The
coroutine returns a flat dict the calling LLM can reason about
(``text`` / ``success`` / ``steps_count`` / ``partial`` / ``error``).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Iterable, TypedDict
from uuid import uuid4

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

if TYPE_CHECKING:
    from leagent.agent.controller import AgentController
    from leagent.agent.query_engine import QueryEngine
    from leagent.tools.executor import ToolExecutor
    from leagent.tools.registry import ToolRegistry


logger = structlog.get_logger(__name__)

DEFAULT_AGENT_TOOL_DENIED_TOOLS: frozenset[str] = frozenset({
    "project_write",
    "project_edit",
    "project_apply_patch",
    "project_shell",
    "code_execution",
    "coding_agent",
    "coding_project_scaffold",
    "coding_project_run",
    "coding_project_stop",
})


class SubagentResult(TypedDict, total=False):
    text: str
    success: bool
    steps_count: int
    partial: bool
    error: str | None
    activity: list[dict[str, Any]]
    changed_files: list[str]
    produced_files: list[dict[str, Any]]
    images: list[dict[str, Any]]
    verification_gap: str | None


def make_child_executor(
    parent_executor: "ToolExecutor",
    child_registry: "ToolRegistry",
) -> "ToolExecutor":
    """Build a :class:`~leagent.tools.executor.ToolExecutor` scoped to ``child_registry``.

    Copies permission and service wiring from ``parent_executor`` so
    sub-agent tool calls enforce the same deployment policy while
    resolving tools **only** from the filtered registry (matching the LLM
    tool schema).
    """
    from leagent.tools.executor import ToolExecutor

    return ToolExecutor(
        registry=child_registry,
        default_timeout=parent_executor.default_timeout,
        max_parallel=getattr(parent_executor, "_max_parallel", 10),
        permission_context=getattr(parent_executor, "_permission_context", None),
        service_manager=parent_executor.service_manager,
    )


def fork_scoped_engine(
    parent_engine: "QueryEngine",
    *,
    child_registry: "ToolRegistry",
    prompt_variant: str,
    system_prompt: str | None = None,
) -> "QueryEngine":
    """Fork with an executor bound to ``child_registry`` (authoritative tool lookup)."""
    ex = getattr(parent_engine.config, "executor", None)
    if ex is None:
        from leagent.tools.executor import ToolExecutor

        scoped = ToolExecutor(registry=child_registry, service_manager=None)
    else:
        scoped = make_child_executor(ex, child_registry)
    return parent_engine.fork(
        system_prompt=system_prompt,
        tools=child_registry,
        prompt_variant=prompt_variant,
        executor=scoped,
    )


def _paths_from_unified_diff(diff: str) -> list[str]:
    paths: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            raw = line[4:].strip()
            if raw in ("/dev/null",):
                continue
            normalized = raw.removeprefix("a/").removeprefix("b/").strip()
            if normalized:
                paths.append(normalized)
    return paths


def _primary_tool_path(tool_name: str, inp: dict[str, Any]) -> str | None:
    for key in ("path", "project_path"):
        v = inp.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    if tool_name == "project_apply_patch":
        diff = inp.get("diff")
        if isinstance(diff, str) and diff.strip():
            for p in _paths_from_unified_diff(diff):
                return p
            return None
    return None


def _record_changed_paths(
    tool_name: str,
    inp: dict[str, Any],
    changed: set[str],
) -> None:
    if tool_name == "project_write" or tool_name == "project_edit":
        p = _primary_tool_path(tool_name, inp)
        if p:
            changed.add(p)
    elif tool_name == "project_apply_patch":
        diff = inp.get("diff")
        if isinstance(diff, str):
            for p in _paths_from_unified_diff(diff):
                changed.add(p)


def _public_activity_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        tool = r.get("tool")
        if not tool:
            continue
        pub: dict[str, Any] = {"tool": str(tool)}
        if r.get("path"):
            pub["path"] = r["path"]
        if r.get("summary"):
            pub["summary"] = r["summary"]
        out.append(pub)
    return out


def _filter_registry(
    source: "ToolRegistry",
    *,
    allowed_tools: Iterable[str] | None,
    denied_tools: Iterable[str] | None,
) -> "ToolRegistry":
    """Build a child registry honouring allow/deny lists.

    * ``allowed_tools`` — whitelist. ``None`` means "keep everything the
      parent has enabled". Names missing from the parent are skipped
      silently.
    * ``denied_tools`` — blacklist applied after the whitelist.
    """
    from leagent.tools.registry import ToolRegistry

    registry = ToolRegistry()
    denied = {name.strip() for name in (denied_tools or ())}

    if allowed_tools is None:
        parent_tools = source.get_enabled_tools()
    else:
        parent_tools = []
        for name in allowed_tools:
            tool = source.find_by_name(name)
            if tool is not None:
                parent_tools.append(tool)

    for tool in parent_tools:
        if tool.name in denied:
            continue
        try:
            registry.register(tool)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "subagent_tool_register_failed",
                tool=getattr(tool, "name", None),
                error=str(exc),
            )
    return registry


def _activity_summary(tool_name: str, content: str, ok: bool) -> str:
    """Short, tool-aware summary for nested sub-agent activity UIs."""
    base = "ok" if ok else "error"
    if tool_name == "code_execution":
        try:
            raw = content.strip()
            if raw.startswith("{"):
                d = json.loads(raw)
                if isinstance(d, dict):
                    inner: dict[str, Any] = d
                    if d.get("tool_ok") is False and isinstance(d.get("detail"), dict):
                        inner = d["detail"]
                    st = str(inner.get("status") or "")
                    parts: list[str] = [f"{base}: status={st}"]
                    err = inner.get("error")
                    if isinstance(err, str) and err.strip():
                        parts.append(err.strip()[:160])
                    else:
                        out = str(inner.get("stdout") or "").replace("\n", " ").strip()
                        if out:
                            parts.append(out[:120])
                    return " ".join(parts)[:500]
        except Exception:
            pass
    if tool_name == "project_shell":
        try:
            raw = content.strip()
            if raw.startswith("{"):
                d = json.loads(raw)
                if isinstance(d, dict):
                    rc = d.get("returncode")
                    st = str(d.get("status") or "")
                    argv = d.get("argv")
                    av_s = ""
                    if isinstance(argv, list) and argv:
                        av_s = " " + " ".join(str(a) for a in argv[:4])
                    tail = ""
                    for key in ("stderr", "stdout"):
                        t = str(d.get(key) or "").replace("\n", " ").strip()
                        if t:
                            tail = t[:100]
                            break
                    head = f"{base}: {st} rc={rc}{av_s}"[:420]
                    return (head + (f" | {tail}" if tail else ""))[:500]
        except Exception:
            pass
    snippet = str(content)[:200].replace("\n", " ").strip()
    return (base + (f": {snippet}" if snippet else ""))[:500]


async def _run_engine(
    engine: "QueryEngine",
    prompt: str,
) -> dict[str, Any]:
    """Drive ``engine.submit_message`` to completion, collecting metrics.

    Mirrors the adapter that :meth:`AgentController._run_via_query_engine`
    uses but flattened to what a tool call needs: a text blob and coarse
    success/error signals.

    Also collects ``activity`` (tool / path / short result summary) and
    ``changed_files`` for workspace UIs when the child uses ``project_*``.
    """
    response_text = ""
    tool_calls_count = 0
    partial = False
    error: str | None = None
    activity_rows: list[dict[str, Any]] = []
    changed_paths: set[str] = set()
    produced_files: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    consumer = getattr(engine.config, "nested_sdk_consumer", None)

    async for sdk_msg in engine.submit_message(prompt):
        if consumer is not None:
            try:
                await consumer(sdk_msg)
            except Exception as exc:  # noqa: BLE001
                logger.warning("nested_sdk_consumer_failed", error=str(exc))

        mtype = sdk_msg.type
        data = sdk_msg.data
        if mtype == "stream_delta":
            response_text += data.get("content", "") or ""
        elif mtype == "assistant":
            text = data.get("content") or ""
            if text and text not in response_text:
                response_text = text
        elif mtype == "tool_use":
            tool_calls_count += 1
            name = str(data.get("name") or "")
            inp = data.get("input") or {}
            if not isinstance(inp, dict):
                inp = {}
            tid = str(data.get("id") or "")
            path = _primary_tool_path(name, inp)
            _record_changed_paths(name, inp, changed_paths)
            activity_rows.append(
                {
                    "tool": name,
                    "path": path,
                    "tool_call_id": tid,
                    "summary": None,
                },
            )
        elif mtype == "tool_result":
            tid = str(data.get("tool_use_id") or "")
            ok = bool(data.get("success"))
            content = str(data.get("content") or "")
            try:
                parsed = (
                    json.loads(content)
                    if content.strip().startswith("{")
                    else None
                )
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                inner: dict[str, Any] = parsed
                if parsed.get("tool_ok") is False and isinstance(
                    parsed.get("detail"), dict
                ):
                    inner = parsed["detail"]
                for entry in inner.get("produced_files") or []:
                    if isinstance(entry, dict):
                        produced_files.append(entry)
                for entry in inner.get("images") or []:
                    if isinstance(entry, dict):
                        images.append(entry)
            for j in range(len(activity_rows) - 1, -1, -1):
                if activity_rows[j].get("tool_call_id") == tid:
                    tname = str(activity_rows[j].get("tool") or "")
                    activity_rows[j]["summary"] = _activity_summary(tname, content, ok)
                    break
        elif mtype == "result":
            reason = data.get("reason", "completed")
            if reason != "completed":
                partial = True
                err = data.get("error")
                if err:
                    error = str(err)

    for row in activity_rows:
        row.pop("tool_call_id", None)

    shell_ran = any(str(r.get("tool") or "") == "project_shell" for r in activity_rows)
    variant = getattr(getattr(engine, "config", None), "prompt_variant", None)
    enforce_shell_verify = str(variant or "") == "coding_agent"
    verification_gap: str | None = None
    if (
        enforce_shell_verify
        and changed_paths
        and not shell_ran
        and not partial
        and error is None
    ):
        verification_gap = (
            "Files were modified but project_shell was not run for "
            "verification (tests/lint/typecheck)."
        )
        partial = True
        logger.info(
            "coding_agent_verification_gap",
            changed_files_count=len(changed_paths),
            changed_files_preview=sorted(changed_paths)[:12],
        )

    return {
        "text": response_text,
        "success": error is None and not partial,
        "steps_count": tool_calls_count,
        "partial": partial,
        "error": error,
        "activity": _public_activity_rows(activity_rows),
        "changed_files": sorted(changed_paths),
        "produced_files": produced_files,
        "images": images,
        "verification_gap": verification_gap,
    }


async def _run_subagent_core(
    *,
    parent_controller: "AgentController | None",
    parent_engine: "QueryEngine | None",
    prompt: str,
    prompt_variant: str,
    allowed_tools: Iterable[str] | None,
    denied_tools: Iterable[str] | None = None,
    system_prompt: str | None = None,
    max_turns: int,
    tool_extra: dict[str, Any] | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    max_tool_calls_per_turn: int | None = None,
    cwd: str | None = None,
    inherit_abort: bool = True,
    inherit_authorized_roots: bool = True,
    log_event: str = "subagent_fork",
    log_fields: dict[str, Any] | None = None,
    nested_preview_emit: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    parent_tool_call_id: str | None = None,
) -> SubagentResult:
    """Shared child-QueryEngine runner used by script/coding sub-agents."""
    from leagent.agent.controller import AgentController
    from leagent.agent.query_engine import QueryEngine, QueryEngineConfig

    parent_eng: QueryEngine
    parent_abort: asyncio.Event | None = None

    if parent_engine is not None:
        parent_eng = parent_engine
        parent_abort = parent_engine.abort_event
    elif parent_controller is not None:
        if not isinstance(parent_controller, AgentController):
            raise TypeError(
                "_run_subagent_core expects an AgentController or QueryEngine, "
                f"got {type(parent_controller).__name__}"
            )
        parent_abort = getattr(parent_controller, "_abort_event", None)
        parent_eng = QueryEngine(
            QueryEngineConfig(
                cwd=cwd or ".",
                llm=parent_controller.llm,
                tools=parent_controller.tools,
                executor=parent_controller.executor,
                agent_memory=parent_controller.agent_memory,
                hooks=getattr(parent_controller, "_hooks", None),
                max_turns=max_turns,
                temperature=parent_controller.config.temperature,
                model_provider=parent_controller.config.model_provider,
                model_name=parent_controller.config.model_name,
                abort_event=parent_abort,
            )
        )
    else:
        raise ValueError("_run_subagent_core requires a parent controller or engine")

    child_registry = _filter_registry(
        parent_eng.config.tools,
        allowed_tools=allowed_tools,
        denied_tools=denied_tools,
    )
    child = fork_scoped_engine(
        parent_eng,
        child_registry=child_registry,
        prompt_variant=prompt_variant,
        system_prompt=system_prompt,
    )
    child.config.max_turns = max_turns
    if cwd is not None:
        child.config.cwd = cwd
    if temperature is not None:
        child.config.temperature = temperature
    if max_output_tokens is not None:
        child.config.max_output_tokens = max_output_tokens
    if max_tool_calls_per_turn is not None:
        child.config.max_tool_calls_per_turn = max_tool_calls_per_turn
    if tool_extra:
        child_extra = dict(child.config.tool_extra or {})
        child_extra.update(tool_extra)
        if inherit_authorized_roots:
            parent_extra = getattr(parent_eng.config, "tool_extra", None) or {}
            parent_auth = parent_extra.get("authorized_roots")
            if isinstance(parent_auth, list) and parent_auth:
                merged_auth = [
                    x
                    for x in child_extra.get("authorized_roots") or []
                    if isinstance(x, str)
                ]
                for item in parent_auth:
                    if (
                        isinstance(item, str)
                        and item.strip()
                        and item not in merged_auth
                    ):
                        merged_auth.append(item)
                if merged_auth:
                    child_extra["authorized_roots"] = merged_auth
        child.config.tool_extra = child_extra

    emit = nested_preview_emit
    if emit is None and getattr(parent_eng.config, "tool_extra", None):
        cand = parent_eng.config.tool_extra.get("nested_preview_emit")
        if callable(cand):
            emit = cand

    pid = (parent_tool_call_id or "").strip() or None

    if emit is not None and pid:
        from leagent.agent.deps import _record_tool_delta_emit, _should_emit_tool_delta

        last_nested_emit: dict[int, dict[str, Any]] = {}
        nested_preview_names = frozenset({
            "project_write",
            "project_edit",
            "project_apply_patch",
            "code_execution",
        })

        async def _nested_sdk_consumer(msg: Any) -> None:
            if getattr(msg, "type", None) != "tool_call_delta":
                return
            data = getattr(msg, "data", None)
            if not isinstance(data, dict):
                return
            name = str(data.get("name") or "").strip()
            if name not in nested_preview_names:
                return
            idx = int(data.get("index", 0) or 0)
            raw = str(data.get("arguments_raw") or "")
            if not _should_emit_tool_delta(idx, len(raw), last_nested_emit):
                return
            _record_tool_delta_emit(idx, len(raw), last_nested_emit)
            payload: dict[str, Any] = {
                "parent_tool_call_id": pid,
                "index": idx,
                "name": name,
                "arguments_raw": raw,
            }
            partial = data.get("arguments_partial")
            if partial is not None:
                payload["arguments_partial"] = partial
            await emit(payload)

        child.config.nested_sdk_consumer = _nested_sdk_consumer

    if inherit_abort and parent_abort is not None:
        async def _bridge() -> None:
            await parent_abort.wait()
            child.abort()

        bridge_task: asyncio.Task[Any] | None = asyncio.create_task(_bridge())
    else:
        bridge_task = None

    logger.info(
        log_event,
        parent_session=str(getattr(parent_eng, "session_id", "unknown")),
        sub_session=str(getattr(child, "session_id", uuid4())),
        max_turns=max_turns,
        allowed_tools=(list(allowed_tools) if allowed_tools is not None else None),
        prompt_preview=prompt[:120],
        **(log_fields or {}),
    )

    try:
        return await _run_engine(child, prompt)
    finally:
        if bridge_task is not None and not bridge_task.done():
            bridge_task.cancel()
        if prompt_variant == "coding_agent":
            try:
                parent_eng._context.file_state.merge_from(child._context.file_state)
            except Exception as exc:  # noqa: BLE001
                logger.debug("subagent_file_state_merge_failed", error=str(exc))


async def fork_subagent(
    parent: "AgentController | QueryEngine",
    prompt: str,
    *,
    allowed_tools: Iterable[str] | None = None,
    denied_tools: Iterable[str] | None = None,
    system_prompt: str | None = None,
    prompt_variant: str = "subagent",
    max_turns: int = 10,
    inherit_abort: bool = True,
) -> dict[str, Any]:
    """Spawn a child agent for a subtask and return its flattened result.

    Args:
        parent: Either an :class:`AgentController` or a
            :class:`QueryEngine`. When given a controller, the shared
            infra (LLM / tools / executor) is used to construct a fresh
            :class:`QueryEngine` that the fork branches off.
        prompt: Natural-language subtask description for the child.
        allowed_tools: Whitelist of tool names the child may call. When
            ``None``, the child inherits the parent's enabled tool set.
        denied_tools: Blacklist applied on top of the whitelist.
        system_prompt: Optional override for the child's system prompt.
        max_turns: Safety cap on the child's think-act loop.
        inherit_abort: When ``True`` (default), the child's abort event
            is set whenever the parent's is, so a user cancel cascades.

    Returns:
        ``{"text": str, "success": bool, "steps_count": int,
           "partial": bool, "error": str | None}``
    """
    from leagent.agent.query_engine import QueryEngine

    if isinstance(parent, QueryEngine):
        parent_controller = None
        parent_engine = parent
    else:
        parent_controller = parent
        parent_engine = None

    return await _run_subagent_core(
        parent_controller=parent_controller,
        parent_engine=parent_engine,
        prompt=prompt,
        allowed_tools=allowed_tools,
        denied_tools=denied_tools,
        system_prompt=system_prompt,
        prompt_variant=prompt_variant,
        max_turns=max_turns,
        inherit_abort=inherit_abort,
        log_event="subagent_fork",
    )


# ---------------------------------------------------------------------------
# BaseTool wrapper
# ---------------------------------------------------------------------------


class AgentTool(BaseTool):
    """Expose generic sub-agent delegation to parent agents.

    Parent LLMs call this tool with a natural-language ``prompt`` plus
    optional tool filters to run an isolated think-act loop in a forked
    :class:`QueryEngine`. The result envelope mirrors
    :class:`ScriptAgentTool` so consumers can switch between them without
    reshaping the parent's response handling.
    """

    name = "agent"
    description = (
        "Delegate a subtask to a fresh sub-agent (a forked QueryEngine "
        "with a clean conversation history). Use for subtasks that "
        "benefit from independent reasoning, tool scoping, or isolated "
        "failure domains. Returns the sub-agent's final text plus basic "
        "execution metadata."
    )
    category = ToolCategory.UTIL
    aliases = ["subagent", "delegate"]
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000

    def __init__(
        self,
        parent_controller: "AgentController | None" = None,
        *,
        parent_engine: "QueryEngine | None" = None,
        parent_provider: Callable[[], "AgentController | None"] | None = None,
    ) -> None:
        if parent_controller is None and parent_engine is None and parent_provider is None:
            raise ValueError(
                "AgentTool requires a parent_controller, parent_engine, or parent_provider"
            )
        self._parent_controller = parent_controller
        self._parent_engine = parent_engine
        self._parent_provider = parent_provider

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "Subtask description for the sub-agent. Include "
                        "any inputs (URIs, column names, constraints) "
                        "directly in the prompt."
                    ),
                },
                "max_turns": {
                    "type": "integer",
                    "description": "Reasoning-turn budget for the sub-agent.",
                    "minimum": 1,
                    "maximum": 30,
                },
                "allowed_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional whitelist of tool names the sub-agent "
                        "may call. Omit to inherit the parent's tool set."
                    ),
                },
                "denied_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional blacklist applied on top of the "
                        "whitelist (or the full inherited set)."
                    ),
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        prompt = params.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("'prompt' must be a non-empty string")

        parent: "AgentController | QueryEngine"
        if self._parent_engine is not None:
            parent = self._parent_engine
        elif self._parent_controller is not None:
            parent = self._parent_controller
        elif self._parent_provider is not None:
            provided_parent = self._parent_provider()
            if provided_parent is None:
                return {"error": "AgentTool has no parent configured"}
            parent = provided_parent
        else:  # unreachable given the constructor guard
            return {"error": "AgentTool has no parent configured"}

        max_turns = int(params.get("max_turns") or 10)
        allowed = params.get("allowed_tools")
        denied = params.get("denied_tools")
        denied_names = {
            name
            for name in (denied if isinstance(denied, list) else [])
            if isinstance(name, str)
        }
        denied_names.update(DEFAULT_AGENT_TOOL_DENIED_TOOLS)

        logger.info(
            "agent_tool_invoke",
            session=str(getattr(parent, "session_id", uuid4())),
            max_turns=max_turns,
            prompt_preview=prompt[:120],
        )

        return await fork_subagent(
            parent,
            prompt,
            allowed_tools=list(allowed) if isinstance(allowed, list) else None,
            denied_tools=sorted(denied_names),
            system_prompt=None,
            max_turns=max_turns,
            inherit_abort=True,
        )


__all__ = [
    "SubagentResult",
    "fork_subagent",
    "_run_subagent_core",
    "fork_scoped_engine",
    "make_child_executor",
    "AgentTool",
]
