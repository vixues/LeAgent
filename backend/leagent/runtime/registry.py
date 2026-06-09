"""Agent definition registry.

The :class:`AgentRegistry` is the lookup surface for declarative
:class:`AgentDefinition` objects. Built-in agents (``default_agent``,
``coding_agent``, ``script_agent``, ``subagent``) mirror the personas that
were previously expressed only as ``prompt_variant`` strings + scattered
constructor wiring. Domain agents register additional definitions here
(directly, via :class:`AgentBuilder`, or loaded from YAML config).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leagent.runtime.builder import AgentBuilder
from leagent.utils.logging import get_logger

if TYPE_CHECKING:
    from leagent.runtime.definition import AgentDefinition

logger = get_logger(__name__)


class AgentRegistry:
    """In-memory registry of :class:`AgentDefinition` keyed by name."""

    def __init__(self) -> None:
        self._defs: dict[str, AgentDefinition] = {}

    def register(self, definition: AgentDefinition, *, replace: bool = False) -> None:
        name = definition.name
        if name in self._defs and not replace:
            raise ValueError(f"Agent '{name}' is already registered")
        self._defs[name] = definition

    def get(self, name: str) -> AgentDefinition:
        try:
            return self._defs[name]
        except KeyError as exc:  # noqa: PERF203
            raise KeyError(
                f"Unknown agent '{name}'. Registered: {sorted(self._defs)}"
            ) from exc

    def try_get(self, name: str) -> AgentDefinition | None:
        return self._defs.get(name)

    def has(self, name: str) -> bool:
        return name in self._defs

    def all(self) -> list[AgentDefinition]:
        return list(self._defs.values())

    def names(self) -> list[str]:
        return sorted(self._defs)

    def __len__(self) -> int:
        return len(self._defs)


def _builtin_definitions() -> list[AgentDefinition]:
    """Return the built-in agent definitions.

    Tool whitelists for the coding/script sub-agents are sourced from their
    canonical defaults so the SDK stays a single source of truth.
    """
    from leagent.agent.coding_agent import DEFAULT_CODING_AGENT_TOOLS
    from leagent.agent.script_agent import DEFAULT_SCRIPT_AGENT_TOOLS

    default_agent = (
        AgentBuilder("default_agent")
        .describe("General-purpose LeAgent office assistant")
        .variant("default_agent")
        .model(task="chat", temperature=0.1, max_output_tokens=8192)
        .memory(enabled=True, recall_limit=6, formation=True)
        .runtime(profile="standard")
        .subagents("coding_agent", "script_agent", "subagent")
        .build()
    )

    coding_agent = (
        AgentBuilder("coding_agent")
        .describe("Project-scale software engineering sub-agent")
        .variant("coding_agent")
        .tools(allow=list(DEFAULT_CODING_AGENT_TOOLS), max_tools=25)
        .model(task="chat", temperature=0.2, max_output_tokens=8192)
        .memory(enabled=True, recall_limit=4, formation=False)
        .runtime(profile="coding_long", max_turns=40, max_tool_calls_per_turn=8)
        .metadata(kind="subagent")
        .build()
    )

    script_agent = (
        AgentBuilder("script_agent")
        .describe("Sandboxed Python compute / data sub-agent")
        .variant("script_agent")
        .tools(allow=list(DEFAULT_SCRIPT_AGENT_TOOLS), max_tools=25)
        .model(task="chat", temperature=0.2, max_output_tokens=4096)
        .memory(enabled=False, formation=False)
        .runtime(profile="standard", max_turns=15, max_tool_calls_per_turn=6)
        .metadata(kind="subagent")
        .build()
    )

    subagent = (
        AgentBuilder("subagent")
        .describe("General delegation sub-agent")
        .variant("subagent")
        .model(task="chat", temperature=0.1, max_output_tokens=8192)
        .memory(enabled=False, formation=False)
        .runtime(profile="standard", max_turns=10)
        .metadata(kind="subagent")
        .build()
    )

    return [default_agent, coding_agent, script_agent, subagent]


def register_builtin_agents(registry: AgentRegistry, *, replace: bool = True) -> None:
    """Register the built-in agent definitions into ``registry``."""
    for definition in _builtin_definitions():
        registry.register(definition, replace=replace)


_REGISTRY: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    """Return the process-wide agent registry, initialising built-ins lazily."""
    global _REGISTRY
    if _REGISTRY is None:
        registry = AgentRegistry()
        try:
            register_builtin_agents(registry)
        except Exception:  # noqa: BLE001 - never let registry init crash startup
            logger.warning("agent_registry_builtin_init_failed", exc_info=True)
        _REGISTRY = registry
    return _REGISTRY


def reset_agent_registry() -> None:
    """Reset the global registry (test helper)."""
    global _REGISTRY
    _REGISTRY = None


def load_agents_from_yaml(
    path: str,
    *,
    registry: AgentRegistry | None = None,
    replace: bool = True,
) -> list[str]:
    """Load agent definitions from a YAML config file.

    Each top-level key is treated as an agent name; its value is a dict
    matching the :class:`AgentDefinition` fields.  Returns the list of
    loaded agent names.

    Example YAML::

        support_agent:
          description: Customer support specialist
          prompt_variant: default_agent
          tools:
            allow: [web_search, knowledge_*]
          model:
            temperature: 0.3
    """
    import yaml

    from leagent.runtime.definition import AgentDefinition

    target = registry if registry is not None else get_agent_registry()

    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ValueError(f"Expected YAML mapping at root, got {type(raw).__name__}")

    loaded: list[str] = []
    for name, fields in raw.items():
        if not isinstance(fields, dict):
            logger.warning("agent_yaml_skip", name=name, reason="not a mapping")
            continue
        fields.setdefault("name", name)
        try:
            definition = AgentDefinition(**fields)
            target.register(definition, replace=replace)
            loaded.append(definition.name)
        except Exception:
            logger.warning("agent_yaml_load_failed", name=name, exc_info=True)

    return loaded


__all__ = [
    "AgentRegistry",
    "get_agent_registry",
    "load_agents_from_yaml",
    "register_builtin_agents",
    "reset_agent_registry",
]
