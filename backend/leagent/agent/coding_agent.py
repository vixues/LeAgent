"""Project-scale coding sub-agent.

Where ``script_agent`` (see :mod:`leagent.agent.script_agent`) is a
single-snippet **compute** agent — it reasons about a question, runs
small Python in a subprocess sandbox, and returns evidence — this
module is the **engineering** counterpart: a ReAct loop wired to the
``project_*`` tool family so the LLM can author, refactor, and verify
multi-file projects on real on-disk paths.

Mental model
------------

1. The parent agent calls :class:`CodingAgentTool` with a natural
   language ``prompt`` plus an absolute ``project_path`` for the
   target repository.
2. The tool builds a fresh :class:`~leagent.agent.query_engine.QueryEngine`
   forked off the parent (or a synthesised one if the caller is an
   :class:`~leagent.agent.controller.AgentController`).
3. ``project_path`` is stamped onto the engine's
   :attr:`QueryEngineConfig.tool_extra` under ``project_roots``. The
   sandbox in :mod:`leagent.tools._sandbox.paths` reads that key
   and folds the directory into the per-request allow-list, so the
   project tools can read/write inside it without widening the
   global ``LEAGENT_TOOL_FILE_ROOTS`` env.
4. The child engine runs with the ``coding_agent`` prompt variant
   and the :data:`DEFAULT_CODING_AGENT_TOOLS` whitelist. It iterates
   on ``project_*`` calls, optional Python via ``code_execution``,
   and curated shell via ``project_shell``, until the task finishes
   or the turn budget is exhausted.

Public surface
--------------

* :data:`DEFAULT_CODING_AGENT_TOOLS` — tool allow-list.
* :func:`build_coding_agent_registry` — filtered registry helper.
* :func:`build_coding_agent_engine` — :class:`QueryEngine` factory.
* :class:`CodingAgentTool` — ``BaseTool`` wrapper for the parent.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Iterable
from uuid import UUID

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from leagent.agent.controller import AgentController
    from leagent.agent.query_engine import QueryEngine
    from leagent.llm import LLMService
    from leagent.memory import AgentMemory
    from leagent.services.service_manager import ServiceManager

logger = structlog.get_logger(__name__)


#: Tools the coding agent is allowed to see. The list is intentionally
#: lean so the LLM doesn't get distracted by side-tools that don't fit
#: the coding mental model. Callers can widen it per invocation.
DEFAULT_CODING_AGENT_TOOLS: tuple[str, ...] = (
    # Project FS layer
    "project_read",
    "project_write",
    "project_edit",
    "project_apply_patch",
    "project_grep",
    "project_glob",
    "project_tree",
    "project_outline",
    "project_shell",
    "deepseek_fim",
    "syntax_validator",
    "tool_argument_blob",
    # Coding-project supervisor (live preview / dev server lifecycle)
    "coding_project_scaffold",
    "coding_project_run",
    "coding_project_stop",
    "coding_project_status",
    "coding_project_read",
    "coding_project_logs",
    # Ad-hoc Python — for data inspection / fixture generation
    "code_execution",
    "uv_pip_install",
    # Reading user-attached specs (README PDFs, requirements docs)
    "pdf_reader",
    "word_reader",
    "excel_reader",
    "csv_processor",
    # Light parsing utilities the agent occasionally needs
    "json_parser",
    "text_splitter",
    "date_calculator",
)


def build_coding_agent_registry(
    source_registry: ToolRegistry,
    *,
    allowed_tools: Iterable[str] = DEFAULT_CODING_AGENT_TOOLS,
) -> ToolRegistry:
    """Build a child :class:`ToolRegistry` exposing only the listed tools.

    Tools missing from the source registry are skipped silently — this
    lets a deployment without (say) PDF readers still launch the
    coding agent without the registration call failing.
    """
    registry = ToolRegistry()
    for name in allowed_tools:
        try:
            tool = source_registry.find_by_name(name)
        except Exception:  # noqa: BLE001
            tool = None
        if tool is None:
            continue
        try:
            registry.register(tool)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "coding_agent_tool_register_skip",
                tool=name,
                error=str(exc),
            )
    return registry


def build_coding_agent_engine(
    *,
    llm: "LLMService",
    tools: ToolRegistry,
    project_path: str,
    cwd: str | None = None,
    system_prompt: str | None = None,
    append_system_prompt: str = "",
    prompt_variant: str = "coding_agent",
    allowed_tools: Iterable[str] = DEFAULT_CODING_AGENT_TOOLS,
    agent_memory: "AgentMemory | None" = None,
    hooks: Any = None,
    service_manager: "ServiceManager | None" = None,
    model_tier: str = "tier1",
    max_turns: int = 40,
    max_tool_calls_per_turn: int = 8,
    temperature: float | None = 0.2,
    max_output_tokens: int | None = 8192,
    user_id: UUID | None = None,
    session_id: UUID | None = None,
    workflow_node_id: str | None = None,
    extra_tool_context: dict[str, Any] | None = None,
) -> "QueryEngine":
    """Return a :class:`QueryEngine` configured as a coding sub-agent.

    The most important parameter is ``project_path`` — an absolute
    path to the on-disk project directory the agent will operate on.
    It is stamped into :attr:`QueryEngineConfig.tool_extra` under
    ``project_roots`` so the path sandbox accepts it (see
    :func:`leagent.tools._sandbox.paths.PathSandbox.resolve_safe`).
    """
    from pathlib import Path

    from leagent.agent.query_engine import QueryEngine, QueryEngineConfig
    from leagent.tools.executor import ToolExecutor

    project_root = Path(project_path).expanduser().resolve()
    if not project_root.is_dir():
        raise ValueError(
            f"project_path={project_path!r} is not an existing directory."
        )

    child_registry = build_coding_agent_registry(tools, allowed_tools=allowed_tools)
    child_executor = ToolExecutor(
        registry=child_registry,
        service_manager=service_manager,
    )

    agent_id = (
        f"coding_agent/{workflow_node_id}" if workflow_node_id else "coding_agent"
    )

    tool_extra: dict[str, Any] = {"project_roots": [str(project_root)]}
    if extra_tool_context:
        tool_extra.update(extra_tool_context)

    cfg = QueryEngineConfig(
        cwd=cwd or str(project_root),
        llm=llm,
        tools=child_registry,
        executor=child_executor,
        agent_memory=agent_memory,
        hooks=hooks,
        system_prompt=(system_prompt or "").strip(),
        append_system_prompt=append_system_prompt,
        prompt_variant=prompt_variant,
        max_turns=max_turns,
        max_tool_calls_per_turn=max_tool_calls_per_turn,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        model_tier=model_tier,
        agent_id=agent_id,
        user_id=user_id,
        session_id=session_id,
        tool_extra=tool_extra,
    )
    return QueryEngine(cfg)


# ---------------------------------------------------------------------------
# Tool wrapper
# ---------------------------------------------------------------------------


class CodingAgentTool(BaseTool):
    """Expose the project-scale coding agent as a tool.

    Parent agents call this tool with:

    * ``prompt`` — natural language description of the engineering
      task (implement feature X, refactor Y, fix bug Z).
    * ``project_path`` — absolute path to the project root.
    * Optional ``goal_summary``/``allowed_tools``/``max_iterations``/
      ``read_only`` to scope the run.

    The tool forks a fresh :class:`QueryEngine` configured for coding,
    drives it to completion, and returns a flat envelope mirroring
    :class:`~leagent.agent.script_agent.ScriptAgentTool` so consumers
    can use both interchangeably.
    """

    name = "coding_agent"
    description = (
        "Delegate a project-scale software engineering task to the "
        "Coding Agent: a sub-agent that can read, search, edit, "
        "patch, write files, and run build/test/git commands inside "
        "an on-disk project root. Use it whenever the work is bigger "
        "than a single file or needs lint/test verification — pass "
        "the absolute project path plus a clear task description."
    )
    category = ToolCategory.CODE
    aliases = ["dev_agent", "software_agent", "engineer_agent"]
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000

    def __init__(
        self,
        parent_controller: "AgentController | None" = None,
        *,
        parent_engine: "QueryEngine | None" = None,
        allowed_tools: Iterable[str] = DEFAULT_CODING_AGENT_TOOLS,
        max_turns: int = 40,
    ) -> None:
        if parent_controller is None and parent_engine is None:
            raise ValueError(
                "CodingAgentTool requires either parent_controller or parent_engine"
            )
        self._parent_controller = parent_controller
        self._parent_engine = parent_engine
        self._allowed_tools = tuple(allowed_tools)
        self._max_turns = max_turns

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "Engineering task in natural language. Be "
                        "concrete: name the feature, files, expected "
                        "behaviour, and any verification command "
                        "(`pytest -k foo`, `npm test`)."
                    ),
                },
                "project_path": {
                    "type": "string",
                    "description": (
                        "Absolute path to the project root the agent "
                        "should operate on. Required."
                    ),
                },
                "goal_summary": {
                    "type": "string",
                    "description": (
                        "One-sentence summary of the task that will be "
                        "logged for telemetry."
                    ),
                },
                "allowed_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional override of the coding agent's tool "
                        "whitelist."
                    ),
                },
                "max_iterations": {
                    "type": "integer",
                    "description": (
                        "Override the reasoning-turn budget (default "
                        "40, max 80)."
                    ),
                    "minimum": 1,
                    "maximum": 80,
                },
                "read_only": {
                    "type": "boolean",
                    "description": (
                        "When true, restrict the child to read-only "
                        "tools (read/grep/glob/tree). Useful for "
                        "investigation tasks."
                    ),
                    "default": False,
                },
            },
            "required": ["prompt", "project_path"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Delegating to coding agent"

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        prompt = params.get("prompt")
        project_path = params.get("project_path")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("'prompt' must be a non-empty string")
        if not isinstance(project_path, str) or not project_path.strip():
            raise ValueError("'project_path' must be a non-empty absolute path")

        from pathlib import Path

        path = Path(project_path).expanduser()
        if not path.is_absolute():
            return {
                "error": (
                    "`project_path` must be absolute. Got "
                    f"{project_path!r}."
                ),
            }
        try:
            path = path.resolve()
        except OSError as exc:
            return {"error": f"Cannot resolve project_path: {exc}"}
        if not path.is_dir():
            return {"error": f"project_path {project_path!r} is not a directory."}

        max_iter = int(params.get("max_iterations") or self._max_turns)
        max_iter = max(1, min(80, max_iter))
        read_only = bool(params.get("read_only") or False)

        allowed_override = params.get("allowed_tools")
        if isinstance(allowed_override, list) and allowed_override:
            allowed = tuple(str(t) for t in allowed_override)
        elif read_only:
            allowed = (
                "project_read",
                "project_grep",
                "project_glob",
                "project_tree",
            )
        else:
            allowed = self._allowed_tools

        extra = getattr(context, "extra", None) or {}
        nested_emit = extra.get("nested_preview_emit")
        if nested_emit is not None and not callable(nested_emit):
            nested_emit = None
        parent_tc = extra.get("current_tool_call_id")
        parent_tc_str = str(parent_tc).strip() if parent_tc is not None else None

        return await _run_coding_agent(
            parent_controller=self._parent_controller,
            parent_engine=self._parent_engine,
            prompt=prompt,
            project_path=str(path),
            allowed_tools=allowed,
            max_turns=max_iter,
            goal_summary=params.get("goal_summary"),
            nested_preview_emit=nested_emit,
            parent_tool_call_id=parent_tc_str,
        )


async def _run_coding_agent(
    *,
    parent_controller: "AgentController | None",
    parent_engine: "QueryEngine | None",
    prompt: str,
    project_path: str,
    allowed_tools: Iterable[str],
    max_turns: int,
    goal_summary: str | None,
    nested_preview_emit: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    parent_tool_call_id: str | None = None,
) -> dict[str, Any]:
    """Build a child :class:`QueryEngine` and drive it to completion.

    Mirrors :func:`leagent.agent.subagent.fork_subagent`: forks off
    the parent (preserving LLM, memory, hooks, abort signal) and
    plumbs ``project_path`` into the child's tool context. Results are
    returned in the same flat envelope so the parent doesn't need to
    branch on which sub-agent answered.
    """
    if parent_controller is None and parent_engine is None:
        return {"error": "Coding agent has no parent configured"}

    from leagent.agent.subagent import _run_subagent_core

    parent_cap = 4096
    if parent_engine is not None:
        parent_cap = int(getattr(parent_engine.config, "max_output_tokens", None) or 4096)

    return await _run_subagent_core(
        parent_controller=parent_controller,
        parent_engine=parent_engine,
        prompt=prompt,
        prompt_variant="coding_agent",
        allowed_tools=allowed_tools,
        denied_tools=None,
        max_turns=max_turns,
        tool_extra={"project_roots": [project_path]},
        cwd=project_path,
        temperature=0.2,
        max_output_tokens=min(8192, max(2048, parent_cap)),
        max_tool_calls_per_turn=8,
        inherit_abort=True,
        log_event="coding_agent_invoke",
        log_fields={
            "project_path": project_path,
            "goal_summary": (goal_summary or "")[:200],
        },
        nested_preview_emit=nested_preview_emit,
        parent_tool_call_id=parent_tool_call_id,
    )


__all__ = [
    "DEFAULT_CODING_AGENT_TOOLS",
    "build_coding_agent_registry",
    "build_coding_agent_engine",
    "CodingAgentTool",
]
