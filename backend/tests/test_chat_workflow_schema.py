"""Tests for chat workflow schema validation and digest stability."""

from __future__ import annotations

import pytest

from leagent.chat_workflow.schema import (
    ValidationError,
    chat_workflow_digest,
    parse_chat_workflow_spec,
    resolve_argument_templates,
)
from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.registry import ToolRegistry


class _ReadOnlyEchoTool(BaseTool):
    name = "chat_workflow_test_echo"
    description = "test"
    category = ToolCategory.UTIL
    is_read_only = True

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {"x": {"type": "string"}}}

    async def execute(self, params: dict, context: ToolContext) -> dict:
        return {"ok": True, "params": params}


class _WriteTool(BaseTool):
    name = "chat_workflow_test_write"
    description = "test write"
    category = ToolCategory.UTIL
    is_read_only = False

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict, context: ToolContext) -> dict:
        return {"ok": True}


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(_ReadOnlyEchoTool())
    reg.register(_WriteTool())
    return reg


def test_parse_accepts_read_only_tool(registry: ToolRegistry) -> None:
    raw = {
        "version": 1,
        "title": "Demo",
        "steps": [
            {
                "id": "s1",
                "label": "Echo",
                "action": {"kind": "tool", "tool_id": "chat_workflow_test_echo", "arguments": {"x": "a"}},
            },
        ],
    }
    spec = parse_chat_workflow_spec(raw, registry=registry)
    assert spec.title == "Demo"
    assert len(spec.steps) == 1


def test_parse_rejects_non_read_only(registry: ToolRegistry) -> None:
    raw = {
        "version": 1,
        "title": "Bad",
        "steps": [
            {
                "id": "s1",
                "label": "Write",
                "action": {"kind": "tool", "tool_id": "chat_workflow_test_write", "arguments": {}},
            },
        ],
    }
    with pytest.raises(ValidationError):
        parse_chat_workflow_spec(raw, registry=registry)


def test_digest_stable(registry: ToolRegistry) -> None:
    raw = {
        "version": 1,
        "title": "T",
        "summary": None,
        "steps": [
            {
                "id": "a",
                "label": "L",
                "action": {"kind": "tool", "tool_id": "chat_workflow_test_echo", "arguments": {}},
            },
        ],
    }
    s1 = parse_chat_workflow_spec(raw, registry=registry)
    s2 = parse_chat_workflow_spec(raw, registry=registry)
    assert chat_workflow_digest(s1) == chat_workflow_digest(s2)


def test_resolve_templates() -> None:
    out = resolve_argument_templates(
        {"q": "sid=${session_id}", "nested": {"u": "${user_id}"}},
        session_id="S1",
        user_id="U1",
        user_input="hello",
    )
    assert out["q"] == "sid=S1"
    assert out["nested"]["u"] == "U1"


def test_parse_requires_step(registry: ToolRegistry) -> None:
    with pytest.raises(Exception):
        parse_chat_workflow_spec({"version": 1, "title": "x", "steps": []}, registry=registry)
