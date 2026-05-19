"""End-to-end coverage for :class:`QueryEngine` system-prompt assembly.

The engine delegates to :class:`ContextManager.prepare_turn`. We stub
``query()`` to terminate immediately and inspect
:attr:`QueryEngine._last_built_prompt`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from leagent.agent import query as query_module
from leagent.agent.query_engine import QueryEngine, QueryEngineConfig
from leagent.agent.transitions import Terminal, TerminalReason
from leagent.services.session.state import SessionAttachment
from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.executor import ToolExecutor
from leagent.tools.registry import ToolRegistry


class _TinyTool(BaseTool):
    name = "noop"
    description = "No-op placeholder tool."
    category = ToolCategory.UTIL
    is_concurrency_safe = True
    is_read_only = True

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        return {}


def _build_engine(system_prompt: str = "") -> QueryEngine:
    reg = ToolRegistry()
    reg.register(_TinyTool())
    cfg = QueryEngineConfig(
        cwd=".",
        llm=None,  # type: ignore[arg-type]
        tools=reg,
        executor=ToolExecutor(registry=reg, service_manager=None),
        system_prompt=system_prompt,
        prompt_variant="default_agent",
    )
    return QueryEngine(cfg)


async def _capture_system_prompt(
    engine: QueryEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    async def _fake_query(params):  # noqa: ANN001
        yield Terminal(TerminalReason.COMPLETED, meta={})

    monkeypatch.setattr(query_module, "query", _fake_query, raising=True)

    messages = []
    async for msg in engine.submit_message("hello"):
        messages.append(msg)

    assert engine._last_built_prompt is not None
    return engine._last_built_prompt.system_text


@pytest.mark.asyncio
async def test_default_agent_includes_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _build_engine()
    prompt = await _capture_system_prompt(engine, monkeypatch)

    assert "noop" in prompt
    assert "LeAgent" in prompt


@pytest.mark.asyncio
async def test_persona_override_replaces_template_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _build_engine(system_prompt="Persona text here")
    prompt = await _capture_system_prompt(engine, monkeypatch)
    assert "Persona text here" in prompt
    assert "Available tools" in prompt
    assert "LeAgent, an intelligent office assistant" not in prompt


@pytest.mark.asyncio
async def test_default_agent_includes_session_attachments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attachment_path = tmp_path / "123_report.docx"
    attachment_path.write_text("demo")
    session_id = uuid4()

    class _SessionManager:
        async def list_attachments(self, _session_id):  # noqa: ANN001
            return [
                SessionAttachment(
                    id=uuid4(),
                    session_id=session_id,
                    filename="report.docx",
                    storage_path=str(attachment_path),
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    kind="document",
                    size=4,
                    sha256="abc",
                )
            ]

        def build_attachment_manifest(self, attachments):  # noqa: ANN001
            return "session_attachments_manifest\npath=" + attachments[0].storage_path

    reg = ToolRegistry()
    reg.register(_TinyTool())
    cfg = QueryEngineConfig(
        cwd=".",
        llm=None,  # type: ignore[arg-type]
        tools=reg,
        executor=ToolExecutor(registry=reg, service_manager=None),
        prompt_variant="default_agent",
        session_id=session_id,
        session_manager=_SessionManager(),
    )
    engine = QueryEngine(cfg)
    prompt = await _capture_system_prompt(engine, monkeypatch)
    assert "session_attachments_manifest" in prompt
    assert str(attachment_path) in prompt
