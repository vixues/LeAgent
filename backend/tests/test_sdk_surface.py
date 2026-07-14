"""Tests for the Agent SDK public surface.

Covers:
- SDK imports and version
- Event taxonomy
- Protocol dataclasses
- Checkpoint store
- RunState serialisation
- ToolCallStreamAssembler
- Provider plugin registry
- Transport
- Memory idempotency (via fake backend)
- AgentSession construction
- Context source plugin registry
- YAML agent loading
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from pathlib import Path
from uuid import UUID

import pytest


class TestSDKImports:
    """Ensure the public surface is importable and complete."""

    def test_version(self):
        from leagent.sdk import __version__
        assert __version__ == "0.1.0"

    def test_all_exports_importable(self):
        import leagent.sdk
        for name in leagent.sdk.__all__:
            assert hasattr(leagent.sdk, name), f"Missing export: {name}"

    def test_event_types(self):
        from leagent.sdk import AgentEvent, AgentEventType, AgentResult
        e = AgentEvent(type=AgentEventType.STREAM_DELTA, data={"content": "hi"})
        assert not e.is_terminal
        e2 = AgentEvent(type=AgentEventType.RESULT, data={"reason": "completed"})
        assert e2.is_terminal
        r = AgentResult(session_id="test")
        assert r.success

    def test_runtime_reexport_identity(self):
        from leagent.sdk.events import AgentEvent as SDK
        from leagent.runtime.events import AgentEvent as RT
        assert SDK is RT


class TestProtocols:
    """Test protocol dataclasses."""

    def test_run_context(self):
        from leagent.sdk import RunContext
        rc = RunContext(abort_event=asyncio.Event())
        assert not rc.aborted
        rc.abort_event.set()
        assert rc.aborted
        with pytest.raises(asyncio.CancelledError):
            rc.raise_if_aborted()

    def test_tool_context_from_run_context(self):
        from leagent.sdk import RunContext, ToolContext
        rc = RunContext(
            abort_event=asyncio.Event(),
            session_id=uuid.uuid4(),
            agent_id="test_agent",
        )
        tc = ToolContext.from_run_context(rc)
        assert tc.session_id == rc.session_id
        assert tc.agent_id == rc.agent_id
        assert not tc.aborted

    def test_assembly_request_result(self):
        from leagent.sdk import AssemblyRequest, AssemblyResult
        req = AssemblyRequest(query="hello", agent_id="test")
        assert req.cwd == "."
        result = AssemblyResult(system_prompt="You are helpful", token_estimate=42)
        assert result.token_estimate == 42


class TestCheckpointStore:
    """Test InMemoryCheckpointStore."""

    @pytest.mark.asyncio
    async def test_save_load_delete(self):
        from leagent.sdk import InMemoryCheckpointStore, create_checkpoint
        store = InMemoryCheckpointStore()
        cp = create_checkpoint(
            session_id="s1",
            agent_name="default_agent",
            turn=3,
            reason="awaiting_user_input",
        )
        await store.save(cp)
        loaded = await store.load(cp.checkpoint_id)
        assert loaded is not None
        assert loaded.session_id == "s1"
        assert loaded.turn == 3
        listed = await store.list_for_session("s1")
        assert len(listed) == 1
        await store.delete(cp.checkpoint_id)
        assert await store.load(cp.checkpoint_id) is None


class TestRunState:
    """Test RunState serialisation."""

    def test_round_trip(self):
        from leagent.sdk import RunState
        rs = RunState(
            session_id="test",
            agent_name="coding_agent",
            turn=5,
            reason="completed",
            tool_calls_total=12,
        )
        d = rs.to_checkpoint_dict()
        rs2 = RunState.from_checkpoint_dict(d)
        assert rs2.session_id == "test"
        assert rs2.turn == 5
        assert rs2.is_terminal

    def test_running_not_terminal(self):
        from leagent.sdk import RunState
        rs = RunState(reason="running")
        assert not rs.is_terminal


class TestToolCallStreamAssembler:
    """Test the stream assembler extracted from deps.py."""

    def test_basic_assembly(self):
        from leagent.llm.streaming import ToolCallStreamAssembler
        asm = ToolCallStreamAssembler()
        asm.feed_deltas([{
            "index": 0,
            "id": "call_1",
            "function": {"name": "web_search", "arguments": '{"query":'},
        }])
        asm.feed_deltas([{
            "index": 0,
            "function": {"arguments": '"hello"}'},
        }])
        results = asm.finalize_as_dicts()
        assert len(results) == 1
        assert results[0]["name"] == "web_search"
        assert results[0]["arguments"] == {"query": "hello"}

    def test_multi_slot(self):
        from leagent.llm.streaming import ToolCallStreamAssembler
        asm = ToolCallStreamAssembler()
        asm.feed_deltas([
            {"index": 0, "id": "c1", "function": {"name": "a", "arguments": "{}"}},
            {"index": 1, "id": "c2", "function": {"name": "b", "arguments": "{}"}},
        ])
        results = asm.finalize()
        assert len(results) == 2
        assert results[0].name == "a"
        assert results[1].name == "b"


class TestProviderPlugin:
    """Test the provider plugin registry."""

    def test_builtin_types_registered(self):
        from leagent.llm.provider_plugin import list_provider_types
        types = list_provider_types()
        assert "openai" in types
        assert "anthropic" in types
        assert "deepseek" in types
        assert "custom" in types

    def test_custom_registration(self):
        from leagent.llm.provider_plugin import (
            register_provider_type,
            get_provider_factory,
            reset_provider_registry,
        )
        def my_factory(**kw):
            return "fake"
        register_provider_type("my_type", my_factory, replace=True)
        assert get_provider_factory("my_type") is not None
        reset_provider_registry()
        assert get_provider_factory("my_type") is None


class TestTransport:
    """Test HttpTransport."""

    def test_singleton(self):
        from leagent.llm.transport import get_default_transport, reset_default_transport
        t1 = get_default_transport()
        t2 = get_default_transport()
        assert t1 is t2
        reset_default_transport()
        t3 = get_default_transport()
        assert t3 is not t1

    def test_request_headers(self):
        from leagent.llm.transport import HttpTransport
        t = HttpTransport()
        headers = t.request_headers({"Authorization": "Bearer test"})
        assert "X-Request-Id" in headers
        assert headers["Authorization"] == "Bearer test"

    def test_request_span_propagates_body_exceptions(self):
        """Body errors must not become 'generator didn't stop after throw()'."""
        from leagent.llm.transport import HttpTransport, TransportConfig

        t = HttpTransport(TransportConfig(otel_enabled=True))
        with pytest.raises(ConnectionError, match="boom"):
            with t.request_span("balance", provider="deepseek"):
                raise ConnectionError("boom")

    def test_request_span_noop_when_otel_disabled(self):
        from leagent.llm.transport import HttpTransport, TransportConfig

        t = HttpTransport(TransportConfig(otel_enabled=False))
        with t.request_span("balance") as span:
            assert span is None


class TestMemoryIdempotency:
    """Test the observe_turn deduplication."""

    @pytest.mark.asyncio
    async def test_duplicate_observe_suppressed(self):
        from leagent.memory.fake import FakeAgentMemory
        from leagent.memory.formation import TurnObservation
        mem = FakeAgentMemory()
        obs = TurnObservation(
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            user_text="hello",
            assistant_text="hi",
            tool_names=[],
        )
        d1 = await mem.observe_turn(obs)
        d2 = await mem.observe_turn(obs)
        assert not d1.suppress or d1.reasoning != "duplicate observe_turn"
        assert d2.suppress and d2.reasoning == "duplicate observe_turn"


class TestMemoryLifecycle:
    """Test the lifecycle API on AgentMemory."""

    @pytest.mark.asyncio
    async def test_forget_episode(self):
        from leagent.memory.fake import FakeAgentMemory
        from leagent.memory.types import Episode
        mem = FakeAgentMemory()
        uid = uuid.uuid4()
        ep = Episode(session_id=uuid.uuid4(), user_id=uid, summary="test")
        await mem.record_episode(ep)
        eps = await mem.export_episodes(user_id=uid, limit=10)
        assert len(eps) == 1
        await mem.forget_episode(ep.id)
        eps = await mem.export_episodes(user_id=uid, limit=10)
        assert len(eps) == 0


class TestContextPlugin:
    """Test the context source plugin registry."""

    def test_plugin_registration(self):
        from leagent.context.plugin import (
            register_source,
            get_plugin_sources,
            reset_plugin_registry,
        )

        class FakeSource:
            id = "test_custom"
            kind = "state"

        register_source(FakeSource, replace=True)
        assert "test_custom" in get_plugin_sources()
        reset_plugin_registry()
        assert "test_custom" not in get_plugin_sources()


class TestYAMLAgentLoading:
    """Test load_agents_from_yaml."""

    def test_load_from_file(self, tmp_path):
        from leagent.runtime.registry import (
            AgentRegistry,
            load_agents_from_yaml,
        )
        yaml_content = """\
test_agent:
  description: A test agent for unit tests
  prompt_variant: default_agent
  tools:
    allow:
      - web_search
  model:
    temperature: 0.5
  memory:
    enabled: false
"""
        yaml_file = tmp_path / "agents.yaml"
        yaml_file.write_text(yaml_content)

        registry = AgentRegistry()
        loaded = load_agents_from_yaml(str(yaml_file), registry=registry)
        assert "test_agent" in loaded
        definition = registry.get("test_agent")
        assert definition.description == "A test agent for unit tests"
        assert definition.model.temperature == 0.5
        assert not definition.memory.enabled


class TestMaterializeConfig:
    """Test that _materialize_config wires policy fields."""

    def test_recall_limit_wired(self):
        from leagent.runtime.definition import AgentDefinition, MemoryPolicy
        defn = AgentDefinition(
            name="test",
            memory=MemoryPolicy(enabled=True, recall_limit=3, formation=False),
        )
        assert defn.memory.recall_limit == 3

    def test_tool_policy_deny(self):
        from leagent.runtime.definition import AgentDefinition, ToolPolicy
        defn = AgentDefinition(
            name="test",
            tools=ToolPolicy(deny=["dangerous_*"]),
        )
        assert "dangerous_*" in defn.tools.deny

    def test_builder_flow(self):
        from leagent.sdk import AgentBuilder
        defn = (
            AgentBuilder("my_agent")
            .describe("Test agent")
            .variant("default_agent")
            .tools(allow=["web_search"], deny=["file_*"])
            .model(task="chat", temperature=0.5)
            .memory(enabled=True, recall_limit=4)
            .runtime(max_turns=20)
            .hooks("hook1")
            .subagents("coding_agent")
            .build()
        )
        assert defn.name == "my_agent"
        assert defn.tools.allow == ["web_search"]
        assert defn.tools.deny == ["file_*"]
        assert defn.model.temperature == 0.5
        assert defn.memory.recall_limit == 4
        assert defn.max_turns == 20
        assert defn.hooks == ["hook1"]
        assert defn.subagents == ["coding_agent"]


class TestAgentRegistry:
    """Test registry operations."""

    def test_builtin_agents_registered(self):
        from leagent.sdk import get_agent_registry
        registry = get_agent_registry()
        assert registry.has("default_agent")
        assert registry.has("coding_agent")
        assert registry.has("script_agent")
        assert registry.has("subagent")

    def test_register_and_resolve(self):
        from leagent.sdk import AgentBuilder, AgentRegistry
        registry = AgentRegistry()
        defn = AgentBuilder("custom_agent").describe("Test").build()
        registry.register(defn)
        assert registry.has("custom_agent")
        resolved = registry.get("custom_agent")
        assert resolved.description == "Test"

    def test_duplicate_registration_raises(self):
        from leagent.sdk import AgentBuilder, AgentRegistry
        registry = AgentRegistry()
        defn = AgentBuilder("dup").build()
        registry.register(defn)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(defn)


class TestPlannerBugFix:
    """Verify the .summary -> .text fix in planner."""

    def test_recall_entry_text_access(self):
        from leagent.memory.types import MemoryKind, RecallEntry
        entry = RecallEntry(
            kind=MemoryKind.EPISODIC,
            text="This is a test summary",
            score=0.5,
            source_id=uuid.uuid4(),
        )
        assert hasattr(entry, "text")
        assert entry.text == "This is a test summary"
        assert not hasattr(entry, "summary")
