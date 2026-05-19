"""Single canonical startup path for the tool system.

This module consolidates the three previously-scattered actions:

1. ``ToolRegistry.discover_all()`` — auto-register every tool under
   :mod:`leagent.tools.{doc,web,data,db,gen,integration,util}` that
   follows the "no-args constructor" contract.
2. Manual registration of the curated utility tools whose
   constructors need runtime config (plan/task/cron/workflow/file
   tools, the skill tool, the code-execution tool, MCP bridge etc.).
3. Lifting every registered tool into a dedicated workflow node via
   :func:`leagent.workflow.nodes.register_tool_nodes`.

Entrypoints (HTTP server, CLI, workflow worker, background workers)
call :func:`bootstrap_tools` once at startup with the relevant
optional knobs (custom registry, custom node registry, whether to
also register the :class:`ScriptAgentTool` — which requires a parent
controller and therefore cannot be wired in until the agent exists).

Keeping this in one place makes it trivial to add a new "must-be-in-
every-process" tool: register it here and every deployment picks it
up. Previously the same list was duplicated in ``main.py`` and
``cli/bootstrap.py``, which caused drift (the CLI didn't have some of
the server's new tools).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

import structlog

from leagent.tools.registry import ToolRegistry, get_registry

if TYPE_CHECKING:
    from leagent.agent.controller import AgentController
    from leagent.workflow.nodes.registry import NodeRegistry

logger = structlog.get_logger(__name__)


#: Tool classes whose constructors take no arguments but that live
#: outside the auto-scanned packages, or that must be instantiated
#: explicitly to avoid import ordering issues. The loader skips any
#: that fail to import so a deployment without optional deps (MinIO
#: integration, Paddle OCR, …) still boots cleanly.
_CURATED_UTIL_TOOL_PATHS: tuple[tuple[str, str], ...] = (
    # --- skills ---
    ("leagent.tools.skills.loader", "SkillTool"),
    ("leagent.tools.skills.resource", "SkillResourceTool"),
    ("leagent.tools.skills.script", "SkillScriptTool"),
    # --- util: plan / task / cron / file / misc ---
    ("leagent.tools.util.plan_tools", "EnterPlanModeTool"),
    ("leagent.tools.util.plan_tools", "ExitPlanModeTool"),
    ("leagent.tools.util.plan_tools", "TodoWriteTool"),
    ("leagent.tools.util.plan_tools", "TodoReadTool"),
    ("leagent.tools.util.task_tools", "TaskCreateTool"),
    ("leagent.tools.util.task_tools", "TaskGetTool"),
    ("leagent.tools.util.task_tools", "TaskListTool"),
    ("leagent.tools.util.task_tools", "TaskUpdateTool"),
    ("leagent.tools.util.task_tools", "TaskKillTool"),
    ("leagent.tools.util.task_tools", "TaskOutputTool"),
    ("leagent.tools.util.cron_tools", "CronCreateTool"),
    ("leagent.tools.util.cron_tools", "CronDeleteTool"),
    ("leagent.tools.util.cron_tools", "CronListTool"),
    ("leagent.tools.util.folder_tool", "FolderOperationsTool"),
    ("leagent.tools.util.file_manager", "FileManagerTool"),
    ("leagent.tools.util.json_parser", "JsonParserTool"),
    ("leagent.tools.util.ask_user", "AskUserTool"),
    ("leagent.tools.util.date_calculator", "DateCalculatorTool"),
    ("leagent.tools.util.text_splitter", "TextSplitterTool"),
    ("leagent.tools.util.tool_argument_blob", "ToolArgumentBlobTool"),
    ("leagent.tools.util.cache_manager", "CacheManagerTool"),
    # --- workflow ---
    ("leagent.tools.workflow.chat_workflow", "ChatWorkflowEmitTool"),
    ("leagent.tools.workflow.workflow_embed_emit", "ChatWorkflowEmbedEmitTool"),
    ("leagent.tools.workflow.workflow_crud", "WorkflowListTool"),
    ("leagent.tools.workflow.workflow_crud", "WorkflowRunTool"),
    ("leagent.tools.workflow.workflow_crud", "WorkflowStatusTool"),
    ("leagent.tools.workflow.workflow_crud", "WorkflowCancelTool"),
    ("leagent.tools.workflow.workflow_crud", "WorkflowPauseTool"),
    ("leagent.tools.workflow.workflow_crud", "WorkflowResumeTool"),
    # --- canvas ---
    ("leagent.tools.canvas.canvas_publish", "CanvasPublishTool"),
    ("leagent.tools.canvas.html_guide", "GetHtmlCanvasGuideTool"),
    ("leagent.tools.canvas.genui_guide", "GetGenuiGuideTool"),
    ("leagent.tools.canvas.ui_components", "ListUiComponentsTool"),
    ("leagent.tools.canvas.ui_components", "EmitUiTreeTool"),
    ("leagent.tools.canvas.ui_components", "EmitUiPatchTool"),
    # --- code ---
    ("leagent.tools.code.execution", "CodeExecutionTool"),
    ("leagent.tools.code.deepseek_fim", "DeepSeekFimTool"),
    ("leagent.tools.code.uv_pip_install", "UvPipInstallTool"),
    # --- project (multi-file coding agent toolbox) ---
    ("leagent.tools.project.read", "ProjectReadTool"),
    ("leagent.tools.project.write", "ProjectWriteTool"),
    ("leagent.tools.project.edit", "ProjectEditTool"),
    ("leagent.tools.project.patch", "ProjectApplyPatchTool"),
    ("leagent.tools.project.grep", "ProjectGrepTool"),
    ("leagent.tools.project.glob", "ProjectGlobTool"),
    ("leagent.tools.project.tree", "ProjectTreeTool"),
    ("leagent.tools.project.outline", "ProjectOutlineTool"),
    ("leagent.tools.project.shell", "ProjectShellTool"),
    # --- coding-project supervisor (live preview) ---
    ("leagent.tools.coding_project.tools", "CodingProjectScaffoldTool"),
    ("leagent.tools.coding_project.tools", "CodingProjectRunTool"),
    ("leagent.tools.coding_project.tools", "CodingProjectStopTool"),
    ("leagent.tools.coding_project.tools", "CodingProjectStatusTool"),
    ("leagent.tools.coding_project.tools", "CodingProjectReadTool"),
    ("leagent.tools.coding_project.tools", "CodingProjectLogsTool"),
    # --- image ---
    ("leagent.tools.image.image_generate", "ImageGenerateTool"),
    # --- chart ---
    ("leagent.tools.chart.chart_generator", "ChartGeneratorTool"),
    # --- integration ---
    ("leagent.tools.integration.notification", "NotificationTool"),
)


def _try_register(registry: ToolRegistry, module_path: str, class_name: str) -> bool:
    try:
        import importlib

        module = importlib.import_module(module_path)
        cls = getattr(module, class_name, None)
        if cls is None:
            return False
        instance = cls()
        registry.register(instance, replace=False)
        return True
    except Exception as exc:  # noqa: BLE001 — skip-and-log, never fatal
        logger.debug(
            "bootstrap_tool_skip",
            module=module_path,
            tool=class_name,
            error=str(exc),
        )
        return False


def register_default_tools(
    registry: ToolRegistry | None = None,
    *,
    extras: Iterable[tuple[str, str]] = (),
    run_discovery: bool = True,
) -> ToolRegistry:
    """Populate ``registry`` with the standard leagent tool palette.

    * Runs :meth:`ToolRegistry.discover_all` when ``run_discovery`` is
      true (the default).
    * Adds every entry from :data:`_CURATED_UTIL_TOOL_PATHS` plus any
      caller-supplied ``extras`` (``(module_path, class_name)``).
    * Returns the same registry for fluent chaining. If ``registry`` is
      ``None`` the process-wide default registry is used.
    """
    # ``ToolRegistry`` defines ``__len__``, so an empty registry is
    # falsy — use an explicit ``None`` check instead of truthiness.
    reg = registry if registry is not None else get_registry()

    if run_discovery:
        try:
            from leagent.config.settings import get_settings

            s = get_settings()
            cats: list[str] | None = None
            if s.desktop_mode or getattr(s, "local_mode", False):
                # Skip ``db`` (heavy / often unused in single-machine profile).
                cats = [
                    "doc",
                    "web",
                    "data",
                    "gen",
                    "image",
                    "chart",
                    "integration",
                    "util",
                    "canvas",
                    "workflow",
                    "code",
                    "skills",
                    "project",
                ]
            discovered = reg.discover_all(categories=cats)
            logger.info("bootstrap_tool_discovery", count=discovered)
        except Exception as exc:  # noqa: BLE001
            logger.warning("bootstrap_tool_discovery_failed", error=str(exc))

    registered = 0
    for module_path, class_name in (*_CURATED_UTIL_TOOL_PATHS, *tuple(extras)):
        if _try_register(reg, module_path, class_name):
            registered += 1

    logger.info(
        "bootstrap_curated_tools_registered",
        count=registered,
        total=len(reg.list_tools()),
    )
    return reg


def register_script_agent_tool(
    registry: ToolRegistry,
    parent: "AgentController",
    *,
    name_override: str | None = None,
) -> bool:
    """Register the :class:`ScriptAgentTool` against ``parent``.

    This is a separate call because the tool needs an already-built
    :class:`AgentController`; the standard bootstrap runs before any
    agent exists. Entrypoints that want the snippet/compute sub-agent
    available from the first turn should call this helper once the
    controller is ready. Returns ``True`` on success.
    """
    try:
        from leagent.agent.script_agent import ScriptAgentTool

        tool = ScriptAgentTool(parent_controller=parent)
        if name_override:
            tool.name = name_override  # type: ignore[misc]
        registry.register(tool, replace=True)
        logger.info("bootstrap_script_agent_tool_registered", name=tool.name)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("bootstrap_script_agent_tool_failed", error=str(exc))
        return False


def register_coding_agent_tool(
    registry: ToolRegistry,
    parent: "AgentController | None" = None,
    *,
    parent_engine: Any = None,
    name_override: str | None = None,
) -> bool:
    """Register the :class:`CodingAgentTool` against ``parent``.

    Mirrors :func:`register_script_agent_tool`: needs an already-built
    parent (controller or engine) so the child can fork off it.
    Entrypoints that want the project-scale coding sub-agent
    available from the first turn should call this once their main
    agent is constructed.
    """
    if parent is None and parent_engine is None:
        logger.warning("bootstrap_coding_agent_tool_missing_parent")
        return False
    try:
        from leagent.agent.coding_agent import CodingAgentTool

        tool = CodingAgentTool(
            parent_controller=parent, parent_engine=parent_engine,
        )
        if name_override:
            tool.name = name_override  # type: ignore[misc]
        registry.register(tool, replace=True)
        logger.info("bootstrap_coding_agent_tool_registered", name=tool.name)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("bootstrap_coding_agent_tool_failed", error=str(exc))
        return False


def register_subagent_tool(
    registry: ToolRegistry,
    parent: "AgentController | None" = None,
    *,
    parent_engine: Any = None,
    name_override: str | None = None,
) -> bool:
    """Register the generic :class:`AgentTool` sub-agent delegator.

    Mirrors :func:`register_script_agent_tool` but exposes the
    general-purpose sub-agent (see :mod:`leagent.agent.subagent`) the
    LLM can invoke for any subtask. Either ``parent`` (an
    :class:`AgentController`) or ``parent_engine`` (a
    :class:`QueryEngine`) must be supplied; providing both gives the
    tool an engine-first fast path with controller fallback.

    Returns ``True`` on successful registration.
    """
    if parent is None and parent_engine is None:
        logger.warning("bootstrap_subagent_tool_missing_parent")
        return False
    try:
        from leagent.agent.subagent import AgentTool

        tool = AgentTool(parent_controller=parent, parent_engine=parent_engine)
        if name_override:
            tool.name = name_override  # type: ignore[misc]
        registry.register(tool, replace=True)
        logger.info("bootstrap_subagent_tool_registered", name=tool.name)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("bootstrap_subagent_tool_failed", error=str(exc))
        return False


async def register_workflow_tool_nodes(
    tool_registry: ToolRegistry,
    node_registry: "NodeRegistry | None" = None,
    *,
    custom_dirs: Iterable[str] = (),
) -> dict[str, list[str]]:
    """Run the full workflow-node bootstrap and lift tools as nodes.

    Thin async wrapper around
    :func:`leagent.workflow.nodes.loader.bootstrap` so callers that
    want *only* the node side of things (e.g. a worker that has tools
    already registered in a parent process) can invoke it directly.
    Returns the raw bootstrap summary
    (``builtin`` / ``entrypoints`` / ``fs`` / ``tools``).
    """
    from leagent.workflow.nodes.loader import bootstrap as _bootstrap_nodes

    return await _bootstrap_nodes(
        registry=node_registry,
        tool_registry=tool_registry,
        custom_dirs=list(custom_dirs) or None,
    )


async def bootstrap_tools(
    *,
    tool_registry: ToolRegistry | None = None,
    node_registry: "NodeRegistry | None" = None,
    extras: Iterable[tuple[str, str]] = (),
    register_nodes: bool = True,
    run_discovery: bool = True,
) -> dict[str, Any]:
    """Async one-shot: populate tools + lift them as workflow nodes.

    Parameters
    ----------
    tool_registry:
        Target registry. Defaults to the process-wide singleton.
    node_registry:
        Where to publish generated ``Tool.<name>`` nodes. Defaults to
        the process-wide node registry.
    extras:
        Extra ``(module, class)`` pairs to register after the curated
        set, for site-local tools not in the repo.
    register_nodes:
        When true, call :func:`register_workflow_tool_nodes` after
        populating tools. Disable for environments that only want
        tools (MCP bridges, batch processors).
    run_discovery:
        When false, skip :meth:`ToolRegistry.discover_all` (useful in
        tests that pre-seed the registry with a fake set).

    Returns
    -------
    dict
        Summary ``{"tools": int, "nodes": list[str]}``.
    """
    reg = register_default_tools(
        tool_registry, extras=extras, run_discovery=run_discovery,
    )
    nodes: list[str] = []
    node_summary: dict[str, list[str]] = {}
    if register_nodes:
        try:
            node_summary = await register_workflow_tool_nodes(reg, node_registry)
            nodes = node_summary.get("tools", [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("bootstrap_tool_nodes_failed", error=str(exc))

    return {
        "tools": len(reg.list_tools()),
        "nodes": nodes,
        "node_summary": node_summary,
    }


def bootstrap_tools_sync(**kwargs: Any) -> dict[str, Any]:
    """Synchronous wrapper for environments without an event loop yet."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            raise RuntimeError("bootstrap_tools_sync called from a running loop")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(bootstrap_tools(**kwargs))
