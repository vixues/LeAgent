"""Runtime dependency bundle.

``RuntimeContext`` (aka the agent *services* bundle) collapses the ~15
constructor parameters that ``QueryEngineConfig``/``AgentController`` used to
take individually into one injectable object. The runtime combines a
:class:`RuntimeContext` (the *how to reach services*) with an
:class:`AgentDefinition` (the *what the agent is*) and per-call session
arguments to materialise a concrete engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from leagent.agent.hooks import HookManager
    from leagent.config.settings import ContextSettings
    from leagent.llm import LLMService
    from leagent.memory import AgentMemory
    from leagent.memory.working_scratchpad import WorkingScratchpad
    from leagent.prompts import PromptBuilder
    from leagent.sdk.protocols import CheckpointStore
    from leagent.services.service_manager import ServiceManager
    from leagent.services.session import SessionManager
    from leagent.skills.manager import SkillsManager
    from leagent.tools.base import ToolPermissionContext
    from leagent.tools.executor import ToolExecutor
    from leagent.tools.registry import ToolRegistry


@dataclass
class RuntimeContext:
    """Shared services used to execute any agent definition."""

    llm: LLMService | None = None
    tools: ToolRegistry | None = None
    executor: ToolExecutor | None = None
    agent_memory: AgentMemory | None = None
    session_manager: SessionManager | None = None
    hook_manager: HookManager | None = None
    skills_manager: SkillsManager | None = None
    permission_context: ToolPermissionContext | None = None
    working_scratchpad: WorkingScratchpad | None = None
    context_settings: ContextSettings | None = None
    prompt_builder: PromptBuilder | None = None
    # Pluggable durable-session / checkpoint backend (Codex RolloutRecorder /
    # Claude SessionStore analogue). ``None`` → the runtime supplies an
    # in-memory default; a DB/Redis-backed store can be injected later.
    checkpoint_store: CheckpointStore | None = None

    @classmethod
    def from_service_manager(
        cls,
        sm: ServiceManager,
        *,
        executor: ToolExecutor | None = None,
        hook_manager: HookManager | None = None,
        permission_context: ToolPermissionContext | None = None,
    ) -> RuntimeContext:
        """Build a runtime context from the process :class:`ServiceManager`.

        The tool registry comes from the global registry; the executor is
        built lazily by the runtime when not supplied here.
        """
        from leagent.sdk.kernel.checkpoint import build_checkpoint_store
        from leagent.tools.registry import get_registry

        registry = get_registry()
        skills_manager = None
        try:
            from leagent.skills.manager import get_skills_manager

            skills_manager = get_skills_manager()
        except Exception:  # noqa: BLE001 - skills are optional
            skills_manager = None

        prompt_builder = None
        try:
            from leagent.prompts import get_prompt_builder

            prompt_builder = get_prompt_builder()
        except Exception:  # noqa: BLE001 - prompt builder is resolved lazily downstream
            prompt_builder = None

        if permission_context is None:
            import os as _os

            from leagent.tools.base import ToolPermissionContext

            # Approval flow knobs (Codex-style): opt-in destructive
            # confirmation and static ask-rules, both env-configurable.
            confirm_destructive = _os.environ.get(
                "LEAGENT_APPROVAL_CONFIRM_DESTRUCTIVE", "",
            ).strip().lower() in ("1", "true", "yes", "on")
            ask_rules = [
                r.strip()
                for r in _os.environ.get("LEAGENT_APPROVAL_ASK_RULES", "").split(",")
                if r.strip()
            ]
            # Skill scripts are third-party code: always an approval trigger
            # (Codex `skill_approval` parity). Opt out only explicitly.
            skill_ask_off = _os.environ.get(
                "LEAGENT_APPROVAL_SKILL_SCRIPTS", "",
            ).strip().lower() in ("0", "false", "no", "off")
            if not skill_ask_off and "run_skill_script" not in ask_rules:
                ask_rules.append("run_skill_script")
            permission_context = ToolPermissionContext(
                confirm_destructive=confirm_destructive,
                always_ask_rules=ask_rules,
            )

        if hook_manager is None:
            from leagent.agent.hooks import HookManager, create_default_hooks

            hook_manager = HookManager()
            for hook in create_default_hooks(getattr(sm, "agent_memory", None)):
                hook_manager.register(hook)

        if executor is None:
            from leagent.tools.executor import ToolExecutor

            executor = ToolExecutor(
                registry=registry,
                service_manager=sm,
                permission_context=permission_context,
            )

        # Durable, resumable sessions: back the checkpoint store with the
        # database when one is available, so paused runs survive restarts /
        # workers. Falls back to the runtime's in-memory default otherwise.
        checkpoint_store = build_checkpoint_store(getattr(sm, "database_service", None))

        return cls(
            llm=getattr(sm, "llm_service", None),
            tools=registry,
            executor=executor,
            agent_memory=getattr(sm, "agent_memory", None),
            session_manager=getattr(sm, "session_manager", None),
            hook_manager=hook_manager,
            skills_manager=skills_manager,
            permission_context=permission_context,
            context_settings=getattr(getattr(sm, "settings", None), "context", None),
            prompt_builder=prompt_builder,
            checkpoint_store=checkpoint_store,
        )


__all__ = ["RuntimeContext"]
