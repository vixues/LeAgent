"""Fluent builder for :class:`AgentDefinition`.

The builder is the code-first half of the SDK surface. It produces (or
overrides) a declarative :class:`AgentDefinition`, which remains the source
of truth. Typical usage::

    from leagent.runtime import AgentBuilder

    support_agent = (
        AgentBuilder("support_agent")
        .describe("Customer support specialist")
        .variant("default_agent")
        .tools(allow=["web_search", "knowledge_*"], max_tools=12)
        .model(task="chat", temperature=0.3)
        .memory(recall_limit=8)
        .runtime(profile="standard", max_turns=12)
        .subagents("script_agent")
        .build()
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leagent.runtime.definition import AgentDefinition

if TYPE_CHECKING:
    from collections.abc import Iterable


class AgentBuilder:
    """Mutable builder that constructs/overrides an :class:`AgentDefinition`."""

    def __init__(self, name: str) -> None:
        if not name or not name.strip():
            raise ValueError("AgentBuilder requires a non-empty agent name")
        self._def = AgentDefinition(name=name.strip())

    @classmethod
    def from_definition(cls, definition: AgentDefinition) -> AgentBuilder:
        """Seed a builder from an existing definition for incremental overrides."""
        builder = cls.__new__(cls)
        builder._def = definition.model_copy(deep=True)
        return builder

    # -- persona ---------------------------------------------------------

    def describe(self, description: str) -> AgentBuilder:
        self._def.description = description
        return self

    def variant(self, prompt_variant: str, *, template: str | None = None) -> AgentBuilder:
        self._def.prompt_variant = prompt_variant
        if template is not None:
            self._def.prompt_template_variant = template
        return self

    def recipe(self, context_recipe: str) -> AgentBuilder:
        self._def.context_recipe = context_recipe
        return self

    def system_prompt(self, prompt: str) -> AgentBuilder:
        self._def.system_prompt = prompt
        return self

    def append_system_prompt(self, prompt: str) -> AgentBuilder:
        self._def.append_system_prompt = prompt
        return self

    # -- policies --------------------------------------------------------

    def tools(
        self,
        *,
        allow: Iterable[str] | None = None,
        deny: Iterable[str] | None = None,
        max_tools: int | None = None,
    ) -> AgentBuilder:
        policy = self._def.tools
        if allow is not None:
            policy.allow = [str(p) for p in allow]
        if deny is not None:
            policy.deny = [str(p) for p in deny]
        if max_tools is not None:
            policy.max_tools = int(max_tools)
        return self

    def model(
        self,
        *,
        task: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AgentBuilder:
        policy = self._def.model
        if task is not None:
            policy.task = task
        if provider is not None:
            policy.provider = provider
        if model is not None:
            policy.model = model
        if temperature is not None:
            policy.temperature = temperature
        if max_output_tokens is not None:
            policy.max_output_tokens = max_output_tokens
        return self

    def memory(
        self,
        *,
        enabled: bool | None = None,
        recall_limit: int | None = None,
        formation: bool | None = None,
    ) -> AgentBuilder:
        policy = self._def.memory
        if enabled is not None:
            policy.enabled = bool(enabled)
        if recall_limit is not None:
            policy.recall_limit = int(recall_limit)
        if formation is not None:
            policy.formation = bool(formation)
        return self

    def runtime(
        self,
        *,
        profile: str | None = None,
        max_turns: int | None = None,
        max_tool_calls_per_turn: int | None = None,
    ) -> AgentBuilder:
        if profile is not None:
            self._def.runtime_profile = profile
        if max_turns is not None:
            self._def.max_turns = int(max_turns)
        if max_tool_calls_per_turn is not None:
            self._def.max_tool_calls_per_turn = int(max_tool_calls_per_turn)
        return self

    # -- composition -----------------------------------------------------

    def hooks(self, *names: str) -> AgentBuilder:
        self._def.hooks = [str(n) for n in names]
        return self

    def subagents(self, *names: str) -> AgentBuilder:
        self._def.subagents = [str(n) for n in names]
        return self

    def metadata(self, **values: object) -> AgentBuilder:
        self._def.metadata.update(values)
        return self

    # -- terminal --------------------------------------------------------

    def build(self) -> AgentDefinition:
        """Return a validated, deep-copied definition."""
        return self._def.model_copy(deep=True)


__all__ = ["AgentBuilder"]
