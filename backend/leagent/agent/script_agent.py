"""Script / compute sub-agent — sandboxed Python snippets (not full repo coding).

This agent runs **small, iterative Python** in the ``code_execution``
subprocess workspace. For **project-scale engineering** (multi-file
edits, lint, tests, git) use :mod:`leagent.agent.coding_agent` and
the ``coding_agent`` tool instead.

The script agent's job is narrow:

1. **Help the parent use code correctly.** Expose ``code_execution``
   plus supporting tools (data transforms, file readers, SQL).
2. **Ensure execution succeeds.** Tool results surface errors so the
   next turn can revise.
3. **Integrate with the tool system.** Exposed as :class:`ScriptAgentTool`.
4. **Workflow node.** :func:`build_script_agent_engine` drives a
   :class:`~leagent.agent.query_engine.QueryEngine` like the main chat loop.

Prompt variant: ``leagent/prompts/templates/script_agent.md``.

Public API:

* :data:`DEFAULT_SCRIPT_AGENT_TOOLS`
* :func:`build_script_agent_registry`
* :func:`build_script_execution_agent` — :class:`AgentController` factory (legacy / tests)
* :func:`build_script_agent_engine` — :class:`QueryEngine` factory
* :class:`ScriptAgentTool` — delegates via :func:`~leagent.agent.subagent.fork_subagent` (same execution path as :mod:`leagent.agent.coding_agent`)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable
from uuid import UUID, uuid4

from leagent.agent.subagent import fork_subagent

import structlog

from leagent.agent.base import AgentConfig, AgentMode
from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from leagent.agent.controller import AgentController
    from leagent.agent.query_engine import QueryEngine
    from leagent.llm import LLMService
    from leagent.memory import AgentMemory
    from leagent.services.service_manager import ServiceManager

logger = structlog.get_logger(__name__)


DEFAULT_SCRIPT_AGENT_TOOLS: tuple[str, ...] = (
    "code_execution",
    "tool_argument_blob",
    "deepseek_fim",
    "syntax_validator",
    "uv_pip_install",
    "data_clean",
    "data_transform",
    "data_aggregate",
    "data_merge",
    "data_validate",
    "sql_query",
    "vector_search",
    "json_parser",
    "text_splitter",
    "date_calculator",
    "file_manager",
    "folder_operations",
    "pdf_reader",
    "word_reader",
    "excel_reader",
    "csv_processor",
)


def build_script_agent_registry(
    source_registry: ToolRegistry,
    *,
    allowed_tools: Iterable[str] = DEFAULT_SCRIPT_AGENT_TOOLS,
) -> ToolRegistry:
    """Filtered registry exposing only ``allowed_tools`` (missing names skipped)."""
    registry = ToolRegistry()
    for name in allowed_tools:
        try:
            tool = source_registry.get(name)
        except Exception:  # noqa: BLE001
            tool = None
        if tool is None:
            continue
        registry.register(tool)
    return registry


def build_script_execution_agent(
    *,
    parent: "AgentController",
    allowed_tools: Iterable[str] = DEFAULT_SCRIPT_AGENT_TOOLS,
    max_iterations: int = 15,
) -> "AgentController":
    """Build a child :class:`AgentController` for sandboxed script runs."""
    from leagent.agent.controller import AgentController
    from leagent.tools.executor import ToolExecutor

    config = AgentConfig(
        max_iterations=max_iterations,
        mode=AgentMode.REACT,
        enable_planning=False,
        agent_name="script_agent",
        prompt_variant="script_agent",
    )
    config.model_tier = parent.config.model_tier
    config.temperature = parent.config.temperature

    child_registry = build_script_agent_registry(parent.tools, allowed_tools=allowed_tools)
    service_manager: "ServiceManager | None" = getattr(
        parent.executor, "service_manager", None,
    )
    child_executor = ToolExecutor(
        registry=child_registry,
        service_manager=service_manager,
        permission_context=getattr(parent, "_permission_context", None),
    )

    return AgentController(
        llm=parent.llm,
        tools=child_registry,
        agent_memory=parent.agent_memory,
        session_manager=parent.session_manager,
        planner=parent.planner,
        executor=child_executor,
        workflow_engine=None,
        hook_manager=getattr(parent, "_hooks", None),
        config=config,
        permission_context=getattr(parent, "_permission_context", None),
    )


def build_script_agent_engine(
    *,
    llm: "LLMService",
    tools: ToolRegistry,
    cwd: str,
    system_prompt: str | None = None,
    append_system_prompt: str = "",
    prompt_variant: str = "script_agent",
    allowed_tools: Iterable[str] = DEFAULT_SCRIPT_AGENT_TOOLS,
    agent_memory: "AgentMemory | None" = None,
    hooks: Any = None,
    service_manager: "ServiceManager | None" = None,
    model_tier: str = "tier1",
    max_turns: int = 15,
    max_tool_calls_per_turn: int = 6,
    temperature: float | None = 0.2,
    max_output_tokens: int | None = 4096,
    user_id: UUID | None = None,
    session_id: UUID | None = None,
    workflow_node_id: str | None = None,
) -> "QueryEngine":
    """Return a :class:`QueryEngine` configured as the script/compute sub-agent."""
    from leagent.agent.query_engine import QueryEngine, QueryEngineConfig
    from leagent.tools.executor import ToolExecutor

    child_registry = build_script_agent_registry(tools, allowed_tools=allowed_tools)
    child_executor = ToolExecutor(
        registry=child_registry,
        service_manager=service_manager,
    )

    agent_id = (
        f"script_agent/{workflow_node_id}" if workflow_node_id else "script_agent"
    )

    cfg = QueryEngineConfig(
        cwd=cwd,
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
    )
    return QueryEngine(cfg)


class ScriptAgentTool(BaseTool):
    """Delegate a **snippet / compute** task to the script sub-agent (not repo coding)."""

    name = "script_agent"
    description = (
        "Delegate a focused computation or file-generation task to the "
        "Script Agent: it runs Python in the code_execution sandbox, "
        "retries from stdout/stderr, and returns JSON summaries plus "
        "workspace files. For editing a real project on disk, use "
        "`coding_agent` with `project_path` instead."
    )
    category = ToolCategory.UTIL
    aliases = ["python_agent", "compute_agent", "code_agent"]
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000

    def __init__(
        self,
        parent_controller: "AgentController | None" = None,
        *,
        allowed_tools: Iterable[str] = DEFAULT_SCRIPT_AGENT_TOOLS,
        max_iterations: int = 15,
    ) -> None:
        self._parent = parent_controller
        self._allowed_tools = tuple(allowed_tools)
        self._max_iterations = max_iterations

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "Concrete task for the script agent. Include "
                        "file references, columns/sheets, desired outputs, "
                        "and success criteria."
                    ),
                },
                "max_iterations": {
                    "type": "integer",
                    "description": "Override the agent's reasoning budget.",
                    "minimum": 1,
                    "maximum": 30,
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        if self._parent is None:
            return {"error": "ScriptAgentTool has no parent controller configured"}

        prompt = params.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("'prompt' must be a non-empty string")
        max_iter = int(params.get("max_iterations") or self._max_iterations)

        sub_session = uuid4()
        logger.info(
            "script_agent_invoke",
            parent_session=str(getattr(self._parent, "_current_session_id", "unknown")),
            sub_session=str(sub_session),
            prompt_preview=prompt[:120],
        )

        return await fork_subagent(
            self._parent,
            prompt,
            allowed_tools=list(self._allowed_tools),
            prompt_variant="script_agent",
            max_turns=max_iter,
            inherit_abort=True,
        )


__all__ = [
    "DEFAULT_SCRIPT_AGENT_TOOLS",
    "build_script_agent_registry",
    "build_script_execution_agent",
    "build_script_agent_engine",
    "ScriptAgentTool",
]
