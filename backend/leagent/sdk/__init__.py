"""LeAgent Agent SDK — the single, versioned public surface.

Every caller (chat API, background tasks, CLI, workflow nodes, sub-agent
delegation) interacts with the agent stack through this package.  The
public surface is intentionally narrow and semver-versioned so downstream
code can pin and upgrade with confidence.

Quick start::

    from leagent.sdk import AgentRuntime, AgentBuilder

    runtime = AgentRuntime.from_service_manager(service_manager)
    result = await runtime.run("default_agent", "Summarise this PDF")

    # Define and register a custom agent:
    support = (
        AgentBuilder("support_agent")
        .variant("default_agent")
        .tools(allow=["web_search", "knowledge_*"])
        .build()
    )
    runtime.registry.register(support)

    # Stream events:
    async for event in runtime.stream("support_agent", "Help me"):
        print(event.type, event.data)
"""

from leagent.sdk._version import __version__

# ── Events & Results ────────────────────────────────────────────────────
from leagent.sdk.events import AgentEvent, AgentEventType, AgentResult

# ── Protocols ───────────────────────────────────────────────────────────
from leagent.sdk.protocols import (
    AssemblyRequest,
    AssemblyResult,
    Checkpoint,
    CheckpointStore,
    ContextAssembler,
    EpisodicStoreProtocol,
    LLMClient,
    MemoryStore,
    ProceduralStoreProtocol,
    Provider,
    RecallProvider,
    RunContext,
    SemanticStoreProtocol,
    ToolContext,
)

# ── Definition / Builder / Registry (re-exported from runtime) ──────────
from leagent.runtime.builder import AgentBuilder
from leagent.runtime.context import RuntimeContext
from leagent.runtime.definition import (
    AgentDefinition,
    MemoryPolicy,
    ModelPolicy,
    ToolPolicy,
)
from leagent.runtime.registry import (
    AgentRegistry,
    get_agent_registry,
    load_agents_from_yaml,
    register_builtin_agents,
    reset_agent_registry,
)

# ── Session ──────────────────────────────────────────────────────────────
from leagent.sdk.session import AgentSession, ContextInspector, MemoryInspector

# ── Kernel ───────────────────────────────────────────────────────────────
from leagent.sdk.kernel.checkpoint import (
    InMemoryCheckpointStore,
    SQLCheckpointStore,
    build_checkpoint_store,
    create_checkpoint,
)
from leagent.sdk.kernel.loop import run_loop
from leagent.sdk.kernel.state import RunState

# ── Runtime facade (re-exported from runtime) ───────────────────────────
from leagent.runtime.runtime import AgentRuntime, get_delegation_runtime

__all__ = [
    # version
    "__version__",
    # events
    "AgentEvent",
    "AgentEventType",
    "AgentResult",
    # protocols
    "AssemblyRequest",
    "AssemblyResult",
    "Checkpoint",
    "CheckpointStore",
    "ContextAssembler",
    "EpisodicStoreProtocol",
    "LLMClient",
    "MemoryStore",
    "ProceduralStoreProtocol",
    "Provider",
    "RecallProvider",
    "RunContext",
    "SemanticStoreProtocol",
    "ToolContext",
    # definition
    "AgentDefinition",
    "AgentBuilder",
    "AgentRegistry",
    "ToolPolicy",
    "ModelPolicy",
    "MemoryPolicy",
    "get_agent_registry",
    "load_agents_from_yaml",
    "register_builtin_agents",
    "reset_agent_registry",
    # runtime context
    "RuntimeContext",
    # session
    "AgentSession",
    "ContextInspector",
    "MemoryInspector",
    # kernel
    "InMemoryCheckpointStore",
    "SQLCheckpointStore",
    "build_checkpoint_store",
    "run_loop",
    "RunState",
    "create_checkpoint",
    # runtime facade
    "AgentRuntime",
    "get_delegation_runtime",
]
