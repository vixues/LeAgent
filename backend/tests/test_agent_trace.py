"""Tests for the durable agent running-trace plane."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest

from leagent.agent.query_engine import SDKMessage
from leagent.db.models.base import utc_now
from leagent.sdk.events import AgentEvent
from leagent.sdk.kernel.loop import run_loop
from leagent.sdk.kernel.state import RunState
from leagent.telemetry.trace.context import clear_trace_context, current_run_id
from leagent.telemetry.trace.export import build_span_tree, export_trace_jsonl
from leagent.telemetry.trace.models import dumps_json, loads_json, prompt_hash
from leagent.telemetry.trace.recorder import TraceRecorder
from leagent.telemetry.trace.store import TraceStore


class _MemStore:
    """Minimal async store used by TraceRecorder unit tests."""

    def __init__(self) -> None:
        self.traces: dict[str, dict[str, Any]] = {}
        self.spans: list[dict[str, Any]] = []

    async def create_trace(self, **kwargs: Any) -> Any:
        tid = kwargs["trace_id"]
        self.traces[tid] = {
            **kwargs,
            "status": "running",
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_miss_tokens": 0,
            "total_cost_usd": 0.0,
            "tool_call_count": 0,
            "llm_call_count": 0,
            "error": None,
            "terminal_reason": None,
            "latency_ms": 0.0,
            "ended_at": None,
            "model": kwargs.get("model") or "",
            "agent_name": kwargs.get("agent_name") or "",
            "started_at": kwargs.get("started_at") or utc_now(),
            "experiment_id": kwargs.get("experiment_id"),
            "prompt_hash": kwargs.get("prompt_hash"),
            "tags": dumps_json(kwargs.get("tags")),
            "scores": None,
            "root_span_id": kwargs.get("root_span_id"),
            "parent_trace_id": kwargs.get("parent_trace_id"),
            "session_id": kwargs.get("session_id"),
            "user_id": kwargs.get("user_id"),
            "scope": kwargs.get("scope") or "chat_turn",
        }
        return self.traces[tid]

    async def update_trace(self, trace_id: str, **kwargs: Any) -> None:
        row = self.traces.get(trace_id)
        if row is None:
            return
        for key in (
            "status",
            "terminal_reason",
            "ended_at",
            "latency_ms",
            "model",
            "agent_name",
            "error",
            "scores",
        ):
            if key in kwargs and kwargs[key] is not None:
                row[key] = kwargs[key]
        row["input_tokens"] += int(kwargs.get("incr_input_tokens") or 0)
        row["output_tokens"] += int(kwargs.get("incr_output_tokens") or 0)
        row["cache_read_tokens"] += int(kwargs.get("incr_cache_read_tokens") or 0)
        row["cache_miss_tokens"] += int(kwargs.get("incr_cache_miss_tokens") or 0)
        row["total_cost_usd"] += float(kwargs.get("incr_total_cost_usd") or 0.0)
        row["tool_call_count"] += int(kwargs.get("incr_tool_call_count") or 0)
        row["llm_call_count"] += int(kwargs.get("incr_llm_call_count") or 0)

    async def append_span(self, **kwargs: Any) -> Any:
        self.spans.append(dict(kwargs))
        return kwargs

    async def close_span(self, span_id: str, **kwargs: Any) -> None:
        for span in self.spans:
            if span.get("span_id") == span_id:
                span.update({k: v for k, v in kwargs.items() if v is not None})
                return

    async def get_trace(self, trace_id: str) -> Any:
        row = self.traces.get(trace_id)
        if row is None:
            return None
        return _Row(row)

    async def list_spans(self, trace_id: str) -> list[Any]:
        return [_Row(s) for s in self.spans if s.get("trace_id") == trace_id]


class _Row:
    def __init__(self, data: dict[str, Any]) -> None:
        self.__dict__.update(data)


class _FakeConfig:
    session_id = "sess-1"
    user_id = None
    agent_id = "test_agent"


class _FakeEngine:
    def __init__(self, scripted: list[SDKMessage]) -> None:
        self._scripted = scripted
        self.mutable_messages: list[dict] = []
        self.abort_event = asyncio.Event()
        self.config = _FakeConfig()

    async def submit_message(self, prompt, **kwargs):
        self.mutable_messages.append({"role": "user", "content": str(prompt)})
        for msg in self._scripted:
            yield msg


@pytest.mark.asyncio
async def test_recorder_maps_tool_and_result_events() -> None:
    store = _MemStore()
    rec = TraceRecorder(store=store)  # type: ignore[arg-type]
    clear_trace_context()
    rec.start_trace(
        run_id="run-1",
        session_id="sess-1",
        agent_name="default_agent",
        model="demo-model",
        prompt="hello",
    )
    await asyncio.sleep(0.05)
    assert current_run_id() == "run-1"
    assert "run-1" in store.traces

    rec.on_event(
        AgentEvent(
            type="tool_use",
            data={"id": "tc1", "name": "web_search", "input": {"q": "x"}},
        )
    )
    rec.record_llm(
        provider="demo",
        model="demo-model",
        request_model="demo-model",
        input_tokens=10,
        output_tokens=5,
        latency_ms=12.0,
        run_id="run-1",
    )
    rec.on_event(
        AgentEvent(
            type="tool_result",
            data={
                "tool_use_id": "tc1",
                "name": "web_search",
                "success": True,
                "content": "ok",
                "duration_ms": 3,
            },
        )
    )
    rec.on_event(
        AgentEvent(type="result", data={"reason": "completed", "usage": {}})
    )
    await asyncio.sleep(0.1)

    kinds = [s["kind"] for s in store.spans]
    assert "agent" in kinds
    assert "tool" in kinds
    assert "llm" in kinds
    assert store.traces["run-1"]["status"] == "completed"
    assert store.traces["run-1"]["tool_call_count"] >= 1
    assert store.traces["run-1"]["llm_call_count"] >= 1
    assert store.traces["run-1"]["input_tokens"] == 10
    clear_trace_context()


@pytest.mark.asyncio
async def test_end_trace_is_idempotent() -> None:
    store = _MemStore()
    rec = TraceRecorder(store=store)  # type: ignore[arg-type]
    rec.start_trace(run_id="run-2", session_id="s")
    await asyncio.sleep(0.02)
    rec.end_trace("run-2", status="completed", terminal_reason="completed")
    rec.end_trace("run-2", status="error", terminal_reason="should_not_overwrite")
    await asyncio.sleep(0.05)
    assert store.traces["run-2"]["status"] == "completed"
    clear_trace_context()


@pytest.mark.asyncio
async def test_run_loop_emits_trace_events_without_raising() -> None:
    store = _MemStore()
    rec = TraceRecorder(store=store)  # type: ignore[arg-type]
    rec.start_trace(run_id="run-loop-1", session_id="sess-1")
    await asyncio.sleep(0.02)

    from leagent.telemetry import trace as trace_pkg

    original = trace_pkg.get_trace_recorder
    trace_pkg.get_trace_recorder = lambda: rec  # type: ignore[assignment]
    try:
        engine = _FakeEngine(
            [
                SDKMessage(
                    type="tool_use",
                    data={"id": "t1", "name": "echo", "input": {}},
                ),
                SDKMessage(
                    type="tool_result",
                    data={
                        "tool_use_id": "t1",
                        "name": "echo",
                        "success": True,
                        "content": "hi",
                    },
                ),
                SDKMessage(type="result", data={"reason": "completed", "usage": {}}),
            ]
        )
        state = RunState(session_id="sess-1", agent_name="test_agent")
        events = [ev async for ev in run_loop(engine, "hi", run_state=state)]
        assert events[-1].type == "result"
        await asyncio.sleep(0.1)
        assert any(s["kind"] == "tool" for s in store.spans)
    finally:
        trace_pkg.get_trace_recorder = original
        clear_trace_context()


def test_prompt_hash_and_json_helpers() -> None:
    assert prompt_hash("abc") == prompt_hash("abc")
    assert prompt_hash("abc") != prompt_hash("abd")
    assert loads_json(dumps_json({"a": 1})) == {"a": 1}


def test_build_span_tree_nests_children() -> None:
    root = _Row(
        {
            "span_id": "r",
            "parent_span_id": None,
            "trace_id": "t",
            "seq": 1,
            "kind": "agent",
            "name": "agent",
            "status": "ok",
            "started_at": utc_now(),
            "ended_at": None,
            "latency_ms": 0,
            "attrs": None,
            "input_preview": None,
            "output_preview": None,
            "payload_ref": None,
        }
    )
    child = _Row(
        {
            "span_id": "c",
            "parent_span_id": "r",
            "trace_id": "t",
            "seq": 2,
            "kind": "tool",
            "name": "tool.x",
            "status": "ok",
            "started_at": utc_now(),
            "ended_at": None,
            "latency_ms": 1,
            "attrs": "{}",
            "input_preview": None,
            "output_preview": None,
            "payload_ref": None,
        }
    )
    tree = build_span_tree([root, child])
    assert len(tree) == 1
    assert tree[0]["span_id"] == "r"
    assert tree[0]["children"][0]["span_id"] == "c"


@pytest.mark.asyncio
async def test_export_trace_jsonl_roundtrip(tmp_path) -> None:
    """SQL TraceStore export against an on-disk SQLite database."""
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool
    from sqlmodel import SQLModel
    from sqlmodel.ext.asyncio.session import AsyncSession

    from leagent.db.models.agent_trace import (  # noqa: F401
        AgentTrace,
        AgentTraceExperiment,
        AgentTraceSpan,
    )

    db_path = tmp_path / "trace.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    class _Db:
        def session(self):
            @asynccontextmanager
            async def _cm():
                async with session_factory() as s:
                    try:
                        yield s
                        await s.commit()
                    except Exception:
                        await s.rollback()
                        raise

            return _cm()

    store = TraceStore(db=_Db())
    tid = uuid4().hex
    await store.create_trace(
        trace_id=tid,
        session_id="s1",
        agent_name="a",
        model="m1",
        experiment_id="exp1",
    )
    await store.append_span(
        span_id=uuid4().hex,
        trace_id=tid,
        seq=1,
        kind="agent",
        name="agent.a",
        status="ok",
    )
    await store.update_trace(tid, status="completed", terminal_reason="completed")

    body = await export_trace_jsonl(tid, store=store)
    assert "leagent.agent_trace.v1" in body
    assert tid in body
    assert "span" in body

    await engine.dispose()


@pytest.mark.asyncio
async def test_experiment_store_and_list(tmp_path) -> None:
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool
    from sqlmodel import SQLModel
    from sqlmodel.ext.asyncio.session import AsyncSession

    from leagent.db.models.agent_trace import (  # noqa: F401
        AgentTrace,
        AgentTraceExperiment,
        AgentTraceSpan,
    )

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'exp.db'}",
        poolclass=NullPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    class _Db:
        def session(self):
            @asynccontextmanager
            async def _cm():
                async with session_factory() as s:
                    try:
                        yield s
                        await s.commit()
                    except Exception:
                        await s.rollback()
                        raise

            return _cm()

    store = TraceStore(db=_Db())
    eid = uuid4().hex
    await store.create_experiment(
        experiment_id=eid,
        name="cmp",
        prompt="say hi",
        model_ids=["m1", "m2"],
        created_by="u1",
    )
    t1 = uuid4().hex
    t2 = uuid4().hex
    await store.create_trace(
        trace_id=t1, model="m1", experiment_id=eid, session_id="s"
    )
    await store.create_trace(
        trace_id=t2, model="m2", experiment_id=eid, session_id="s"
    )
    rows = await store.list_traces(experiment_id=eid)
    assert len(rows) == 2
    models = {r.model for r in rows}
    assert models == {"m1", "m2"}
    exp = await store.get_experiment(eid)
    assert exp is not None
    assert loads_json(exp.model_ids) == ["m1", "m2"]
    await engine.dispose()
