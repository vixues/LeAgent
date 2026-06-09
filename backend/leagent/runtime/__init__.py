"""LeAgent Agent Runtime SDK.

The runtime package is the unified, SDK-governed harness for building and
executing domain-specific agents. It centres on three contracts:

* :class:`AgentDefinition` — the declarative source of truth for an agent
  (persona, tool policy, model policy, memory policy, runtime budget,
  composition). Build it directly, via :class:`AgentBuilder`, or load it
  from YAML config into an :class:`AgentRegistry`.
* :class:`RuntimeContext` — the injectable services bundle (LLM, tools,
  executor, memory, session, hooks, …).
* :class:`AgentRuntime` — the single execution facade. It materialises a
  definition + context into the session-scoped query loop and yields a
  unified :class:`AgentEvent` stream / :class:`AgentResult`.

Example::

    from leagent.runtime import AgentRuntime, AgentBuilder

    runtime = AgentRuntime.from_service_manager(service_manager)
    result = await runtime.run("default_agent", "Summarise this PDF")

    # Define a custom domain agent:
    support = (
        AgentBuilder("support_agent")
        .variant("default_agent")
        .tools(allow=["web_search", "knowledge_*"])
        .build()
    )
    runtime.registry.register(support)
"""

from leagent.runtime.builder import AgentBuilder
from leagent.runtime.context import RuntimeContext
from leagent.runtime.definition import (
    AgentDefinition,
    MemoryPolicy,
    ModelPolicy,
    ToolPolicy,
)
from leagent.runtime.events import AgentEvent, AgentEventType, AgentResult
from leagent.runtime.registry import (
    AgentRegistry,
    get_agent_registry,
    load_agents_from_yaml,
    register_builtin_agents,
    reset_agent_registry,
)
from leagent.runtime.runtime import AgentRuntime, get_delegation_runtime

__all__ = [
    "AgentDefinition",
    "ToolPolicy",
    "ModelPolicy",
    "MemoryPolicy",
    "AgentBuilder",
    "AgentRegistry",
    "get_agent_registry",
    "load_agents_from_yaml",
    "register_builtin_agents",
    "reset_agent_registry",
    "RuntimeContext",
    "AgentEvent",
    "AgentEventType",
    "AgentResult",
    "AgentRuntime",
    "get_delegation_runtime",
]
