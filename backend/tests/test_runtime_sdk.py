"""Unit tests for the Agent Runtime SDK contracts.

Covers the declarative :class:`AgentDefinition`, the fluent
:class:`AgentBuilder`, the :class:`AgentRegistry` (including built-ins),
and the unified :class:`AgentEvent` / :class:`AgentResult` wire shape.

These tests are dependency-free: they exercise the SDK surface without a
live ``ServiceManager``/LLM, so they pin the contract that downstream
domain agents and call-site migrations rely on.
"""

from __future__ import annotations

import pytest

from leagent.runtime import (
    AgentBuilder,
    AgentDefinition,
    AgentEvent,
    AgentEventType,
    AgentRegistry,
    AgentResult,
    MemoryPolicy,
    ModelPolicy,
    ToolPolicy,
    get_agent_registry,
    register_builtin_agents,
    reset_agent_registry,
)

# ---------------------------------------------------------------------------
# AgentDefinition
# ---------------------------------------------------------------------------


def test_definition_defaults() -> None:
    d = AgentDefinition(name="x")
    assert d.prompt_variant == "default_agent"
    assert isinstance(d.tools, ToolPolicy)
    assert isinstance(d.model, ModelPolicy)
    assert isinstance(d.memory, MemoryPolicy)
    assert d.model.task == "chat"
    assert d.memory.enabled is True
    assert d.runtime_profile == "standard"


def test_resolved_recipe_falls_back_to_variant() -> None:
    d = AgentDefinition(name="x", prompt_variant="coding_agent")
    assert d.resolved_recipe() == "coding_agent"
    d2 = AgentDefinition(name="x", prompt_variant="coding_agent", context_recipe="lean")
    assert d2.resolved_recipe() == "lean"


def test_with_overrides_is_shallow_and_non_mutating() -> None:
    d = AgentDefinition(name="x", max_turns=5)
    d2 = d.with_overrides(max_turns=20)
    assert d.max_turns == 5
    assert d2.max_turns == 20
    assert d2.name == "x"


def test_with_overrides_replaces_tool_policy() -> None:
    d = AgentDefinition(name="x")
    d2 = d.with_overrides(tools=d.tools.model_copy(update={"allow": ["a", "b"]}))
    assert d.tools.allow == []
    assert d2.tools.allow == ["a", "b"]


# ---------------------------------------------------------------------------
# AgentBuilder
# ---------------------------------------------------------------------------


def test_builder_fluent_chain() -> None:
    d = (
        AgentBuilder("support_agent")
        .describe("Support specialist")
        .variant("default_agent", template="default")
        .recipe("support_recipe")
        .tools(allow=["web_search", "knowledge_*"], deny=["shell"], max_tools=12)
        .model(task="fast", temperature=0.3, max_output_tokens=2048)
        .memory(enabled=True, recall_limit=8, formation=False)
        .runtime(profile="standard", max_turns=12, max_tool_calls_per_turn=4)
        .hooks("logging")
        .subagents("script_agent")
        .metadata(kind="support")
        .build()
    )
    assert d.name == "support_agent"
    assert d.description == "Support specialist"
    assert d.prompt_variant == "default_agent"
    assert d.resolved_recipe() == "support_recipe"
    assert d.tools.allow == ["web_search", "knowledge_*"]
    assert d.tools.deny == ["shell"]
    assert d.tools.max_tools == 12
    assert d.model.task == "fast"
    assert d.model.temperature == 0.3
    assert d.memory.recall_limit == 8
    assert d.memory.formation is False
    assert d.max_turns == 12
    assert d.max_tool_calls_per_turn == 4
    assert d.hooks == ["logging"]
    assert d.subagents == ["script_agent"]
    assert d.metadata["kind"] == "support"


def test_builder_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        AgentBuilder("   ")


def test_builder_build_returns_independent_copy() -> None:
    b = AgentBuilder("x").tools(allow=["a"])
    d1 = b.build()
    b.tools(allow=["b"])
    d2 = b.build()
    assert d1.tools.allow == ["a"]
    assert d2.tools.allow == ["b"]


def test_builder_from_definition_seeds_overrides() -> None:
    base = AgentBuilder("x").variant("coding_agent").build()
    derived = AgentBuilder.from_definition(base).describe("derived").build()
    assert derived.prompt_variant == "coding_agent"
    assert derived.description == "derived"
    assert base.description == ""


# ---------------------------------------------------------------------------
# AgentRegistry
# ---------------------------------------------------------------------------


def test_registry_register_and_lookup() -> None:
    reg = AgentRegistry()
    d = AgentBuilder("x").build()
    reg.register(d)
    assert reg.has("x")
    assert reg.get("x") is d
    assert reg.try_get("missing") is None
    assert "x" in reg.names()
    assert len(reg) == 1


def test_registry_duplicate_requires_replace() -> None:
    reg = AgentRegistry()
    reg.register(AgentBuilder("x").build())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(AgentBuilder("x").build())
    reg.register(AgentBuilder("x").describe("v2").build(), replace=True)
    assert reg.get("x").description == "v2"


def test_registry_get_unknown_raises_keyerror() -> None:
    reg = AgentRegistry()
    with pytest.raises(KeyError, match="Unknown agent"):
        reg.get("nope")


def test_builtin_agents_present() -> None:
    reg = AgentRegistry()
    register_builtin_agents(reg)
    names = set(reg.names())
    assert {"default_agent", "coding_agent", "script_agent", "subagent"} <= names
    coding = reg.get("coding_agent")
    assert coding.tools.allow  # coding agent ships a tool whitelist
    assert coding.memory.formation is False


def test_global_registry_initialises_builtins() -> None:
    reset_agent_registry()
    try:
        reg = get_agent_registry()
        assert reg.has("default_agent")
    finally:
        reset_agent_registry()


# ---------------------------------------------------------------------------
# AgentEvent / AgentResult wire parity
# ---------------------------------------------------------------------------


def test_agent_event_sdk_roundtrip_preserves_wire_shape() -> None:
    from leagent.agent.query_engine import SDKMessage

    msg = SDKMessage(type="tool_use", data={"name": "web_search", "id": "1"})
    event = AgentEvent.from_sdk_message(msg)
    assert event.type == "tool_use"
    assert event.data == {"name": "web_search", "id": "1"}

    back = event.to_sdk_message()
    assert back.type == msg.type
    assert back.data == msg.data


def test_agent_event_terminal_flag() -> None:
    assert AgentEvent(type=AgentEventType.RESULT).is_terminal is True
    assert AgentEvent(type=AgentEventType.STREAM_DELTA).is_terminal is False


def test_agent_event_data_is_copied_not_aliased() -> None:
    from leagent.agent.query_engine import SDKMessage

    src = {"k": "v"}
    msg = SDKMessage(type="assistant", data=src)
    event = AgentEvent.from_sdk_message(msg)
    event.data["k"] = "mutated"
    assert src["k"] == "v"


def test_agent_result_success_semantics() -> None:
    assert AgentResult(session_id="s", reason="completed").success is True
    assert AgentResult(session_id="s", reason="awaiting_user_input").success is True
    assert AgentResult(session_id="s", reason="completed", error="boom").success is False
    assert AgentResult(session_id="s", reason="max_turns").success is False


# ---------------------------------------------------------------------------
# Sub-agent definition fidelity (delegate -> _run_subagent_core)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delegate_threads_definition_policy_to_subagent_core(monkeypatch) -> None:
    """delegate must forward the child's recipe/model/memory policy."""
    import leagent.agent.subagent as subagent_mod
    from leagent.agent.query_engine import QueryEngine, QueryEngineConfig
    from leagent.runtime import AgentRuntime, RuntimeContext

    captured: dict = {}

    async def _fake_core(**kwargs):
        captured.update(kwargs)
        return {"text": "ok", "success": True}

    monkeypatch.setattr(subagent_mod, "_run_subagent_core", _fake_core)

    parent_engine = QueryEngine(QueryEngineConfig())
    rt = AgentRuntime(RuntimeContext())

    definition = (
        AgentBuilder("child")
        .variant("coding_agent")
        .recipe("lean")
        .model(task="fast", provider="openai", model="gpt-x")
        .memory(enabled=False, recall_limit=3, formation=False)
        .tools(max_tools=7)
        .build()
    )

    await rt.delegate(parent_engine, definition, "do the thing")

    assert captured["context_recipe"] == "lean"
    assert captured["model_task"] == "fast"
    assert captured["model_provider"] == "openai"
    assert captured["model_name"] == "gpt-x"
    assert captured["memory_enabled"] is False
    # recall_limit is suppressed when memory is disabled.
    assert captured["recall_limit"] is None
    assert captured["memory_formation"] is False
    assert captured["tools_max_tools"] == 7
