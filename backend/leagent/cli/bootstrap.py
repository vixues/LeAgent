"""CLI-local service bootstrap.

Builds the same **LLM + tool registry + rules + skills** stack the FastAPI app uses
for agent turns, but **without** ``ServiceManager``, database sessions, or signed URL
machinery. The returned :class:`CLIServices` wires an :class:`~leagent.agent.controller.AgentController`
with :class:`~leagent.tools.executor.ToolExecutor` over the global registry so local
``leagent`` / ``-m`` runs exercise the **QueryEngine** execution path inside the controller.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from leagent.agent.controller import AgentController
    from leagent.llm.service import LLMService
    from leagent.rules.engine import RuleEngine
    from leagent.skills.manager import SkillsManager
    from leagent.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)


@dataclass
class CLIServices:
    """In-process services for ``leagent chat`` / ``-m`` (no HTTP, no SessionManager)."""

    llm: LLMService | None = None
    tools: ToolRegistry | None = None
    rules: RuleEngine | None = None
    skills: SkillsManager | None = None
    _agent: AgentController | None = field(default=None, repr=False)

    @property
    def is_ready(self) -> bool:
        return self.llm is not None and self.tools is not None

    def build_agent(self, **overrides: Any) -> AgentController | None:
        """Construct :class:`~leagent.agent.controller.AgentController` (QueryEngine-backed runs)."""
        if not self.is_ready:
            return None
        if self._agent is not None:
            return self._agent

        from leagent.agent.base import AgentConfig
        from leagent.agent.controller import AgentController
        from leagent.agent.planner import TaskPlanner
        from leagent.tools.executor import ToolExecutor

        config = AgentConfig(
            enable_streaming=True,
            mode=overrides.pop("mode", AgentConfig.mode),
            verbose=overrides.pop("verbose", False),
        )

        executor = ToolExecutor(registry=self.tools)
        planner = TaskPlanner(llm=self.llm)

        self._agent = AgentController(
            llm=self.llm,
            tools=self.tools,
            agent_memory=None,
            planner=planner,
            executor=executor,
            config=config,
        )

        try:
            from leagent.bootstrap import (
                register_coding_agent_tool,
                register_script_agent_tool,
                register_subagent_tool,
            )

            register_script_agent_tool(self.tools, self._agent)
            register_coding_agent_tool(self.tools, self._agent)
            register_subagent_tool(self.tools, self._agent)
        except Exception as exc:
            logger.debug("cli_bootstrap_subtool_skip", error=str(exc))

        return self._agent


async def bootstrap_cli_services(
    *,
    load_rules: bool = True,
    load_skills: bool = True,
    debug: bool = False,
) -> CLIServices:
    """Prepare LLM, ``bootstrap_tools()`` registry, rules, and skills for offline CLI use.

    Skips PostgreSQL/session persistence, auth, and :class:`~leagent.services.service_manager.ServiceManager`.
    """
    if debug:
        logging.basicConfig(level=logging.DEBUG)

    services = CLIServices()

    # LLM
    try:
        from leagent.llm.service import LLMService
        services.llm = LLMService.from_settings()
        logger.debug("cli_bootstrap_llm_ok", providers=len(services.llm.list_providers()))
    except Exception as exc:
        logger.warning("cli_bootstrap_llm_failed", error=str(exc))

    # Tools (auto-discovery + curated utility tools + workflow nodes)
    try:
        from leagent.bootstrap import bootstrap_tools

        summary = await bootstrap_tools()
        from leagent.tools.registry import get_registry
        services.tools = get_registry()
        logger.debug(
            "cli_bootstrap_tools_ok",
            count=summary["tools"],
            nodes=len(summary["nodes"]),
        )
    except Exception as exc:
        logger.warning("cli_bootstrap_tools_failed", error=str(exc))

    # Rules
    if load_rules:
        try:
            from pathlib import Path

            from leagent.config.constants import RULES_DIR
            from leagent.config.settings import get_settings
            from leagent.rules.engine import RuleEngine

            raw = (get_settings().rules_directory or "").strip()
            rules_path = Path(raw).expanduser().resolve() if raw else RULES_DIR
            engine = RuleEngine(llm_service=services.llm)
            if rules_path.exists() and any(rules_path.glob("*.yaml")) or any(rules_path.glob("*.yml")):
                await engine.load_rules(rules_path)
            services.rules = engine
            logger.debug("cli_bootstrap_rules_ok", sets=len(engine.list_rule_sets()))
        except Exception as exc:
            logger.warning("cli_bootstrap_rules_failed", error=str(exc))

    # Skills
    if load_skills:
        try:
            from leagent.skills.manager import get_skills_manager
            manager = get_skills_manager()
            await manager.load_all()
            services.skills = manager
            logger.debug("cli_bootstrap_skills_ok", count=len(manager.all_skills))
        except Exception as exc:
            logger.warning("cli_bootstrap_skills_failed", error=str(exc))

    return services

