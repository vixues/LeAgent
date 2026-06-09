"""Declarative agent contract.

``AgentDefinition`` is the single source of truth describing *what* a
domain-specific agent is: its persona/prompt variant, tool access policy,
model routing policy, memory policy, runtime budget, lifecycle hooks, and
which sub-agents it may delegate to.

It is intentionally free of runtime/DI concerns (LLM service, tool
registry, session id, abort event, …). Those live in
:class:`leagent.runtime.context.RuntimeContext` and the per-call arguments
of :class:`leagent.runtime.runtime.AgentRuntime`. The runtime *materialises*
an ``AgentDefinition`` + ``RuntimeContext`` into a concrete
``QueryEngineConfig`` at invocation time.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolPolicy(BaseModel):
    """Declarative tool access policy for an agent.

    Attributes:
        allow: Tool name globs the agent may use. Empty means "all tools
            visible to the runtime registry" (subject to ``deny``).
        deny: Tool name globs that are always hidden, even if matched by
            ``allow``. Mapped onto ``QueryEngineConfig.tools_deny_patterns``.
        max_tools: Upper bound on tools advertised to the model per turn.
    """

    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    max_tools: int = 25


class ModelPolicy(BaseModel):
    """Declarative LLM routing policy.

    ``task`` selects a logical :class:`leagent.llm.model_spec.ModelTask`
    binding from ``providers.yaml`` (e.g. ``chat``/``fast``). An explicit
    ``provider``/``model`` override the task binding when set.
    """

    task: str = "chat"
    provider: str | None = None
    model: str | None = None
    temperature: float | None = 0.1
    max_output_tokens: int | None = 8192


class MemoryPolicy(BaseModel):
    """Declarative cognitive-memory policy.

    Attributes:
        enabled: When false, recall is skipped and ``AgentMemory`` is not
            wired into the materialised engine for this agent.
        recall_limit: Max recall entries to inject per turn.
        formation: When false, the runtime suppresses episodic/semantic/
            procedural writes for this agent's turns.
    """

    enabled: bool = True
    recall_limit: int = 6
    formation: bool = True


class AgentDefinition(BaseModel):
    """The declarative definition of a domain-specific agent.

    This is the formal SDK contract. Build one directly, via
    :class:`leagent.runtime.builder.AgentBuilder`, or load from YAML
    (``leagent.config`` agents) and register it in an
    :class:`leagent.runtime.registry.AgentRegistry`.
    """

    model_config = {"frozen": False}

    name: str
    description: str = ""

    # Persona / prompt assembly
    prompt_variant: str = "default_agent"
    prompt_template_variant: str = "default"
    system_prompt: str = ""
    append_system_prompt: str = ""
    #: Context recipe variant; defaults to ``prompt_variant`` when unset.
    context_recipe: str | None = None

    # Policies
    tools: ToolPolicy = Field(default_factory=ToolPolicy)
    model: ModelPolicy = Field(default_factory=ModelPolicy)
    memory: MemoryPolicy = Field(default_factory=MemoryPolicy)

    # Runtime budget
    runtime_profile: str = "standard"
    max_turns: int | None = None
    max_tool_calls_per_turn: int | None = None

    # Composition
    hooks: list[str] = Field(default_factory=list)
    subagents: list[str] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)

    def resolved_recipe(self) -> str:
        """Return the context recipe to use (falls back to prompt variant)."""
        return self.context_recipe or self.prompt_variant

    def with_overrides(self, **overrides: Any) -> AgentDefinition:
        """Return a copy with shallow field overrides applied."""
        return self.model_copy(update=overrides)


__all__ = [
    "AgentDefinition",
    "ToolPolicy",
    "ModelPolicy",
    "MemoryPolicy",
]
