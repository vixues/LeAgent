"""Tests for chat workflow schema validation and digest stability."""

from __future__ import annotations

import pytest

from leagent.chat_workflow.arguments import (
    coerce_workflow_step_arguments,
    normalize_workflow_step_arguments,
    validate_workflow_step_paths,
)
from leagent.chat_workflow.schema import (
    ValidationError,
    chat_workflow_digest,
    parse_chat_workflow_spec,
    resolve_argument_templates,
)
from leagent.tools.doc.pdf_reader import PDFReaderTool
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


class _DestructiveTool(BaseTool):
    name = "chat_workflow_test_destructive"
    description = "test destructive"
    category = ToolCategory.UTIL
    is_destructive = True

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
    reg.register(_DestructiveTool())
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


def test_parse_accepts_non_destructive_write_tool(registry: ToolRegistry) -> None:
    raw = {
        "version": 1,
        "title": "Write ok",
        "steps": [
            {
                "id": "s1",
                "label": "Write",
                "action": {"kind": "tool", "tool_id": "chat_workflow_test_write", "arguments": {}},
            },
        ],
    }
    spec = parse_chat_workflow_spec(raw, registry=registry)
    assert spec.title == "Write ok"


def test_parse_rejects_destructive_tool(registry: ToolRegistry) -> None:
    raw = {
        "version": 1,
        "title": "Bad",
        "steps": [
            {
                "id": "s1",
                "label": "Destructive",
                "action": {
                    "kind": "tool",
                    "tool_id": "chat_workflow_test_destructive",
                    "arguments": {},
                },
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


def test_coerce_workflow_step_picks_session_pdf(registry: ToolRegistry) -> None:
    registry.register(PDFReaderTool())
    ctx = ToolContext(
        user_id="u1",
        session_id="s1",
        extra={"attachments": ["/home/user/uploads/report.pdf", "/home/user/uploads/notes.txt"]},
    )
    out = coerce_workflow_step_arguments(
        "pdf_reader",
        {"operation": "read", "file_path": ""},
        ctx,
        registry=registry,
    )
    assert out["file_path"] == "/home/user/uploads/report.pdf"


def test_validate_workflow_step_paths_when_still_empty(registry: ToolRegistry) -> None:
    registry.register(PDFReaderTool())
    ctx = ToolContext(user_id="u1", session_id="s1", extra={})
    err = validate_workflow_step_paths(
        "pdf_reader",
        {"operation": "read", "file_path": ""},
        ctx,
        registry=registry,
    )
    assert err is not None
    assert "file_path" in err
    assert "Upload" in err


def test_normalize_csv_source_path_to_file_path(registry: ToolRegistry) -> None:
    from leagent.tools.doc.csv_processor import CSVProcessorTool

    registry.register(CSVProcessorTool())
    out = normalize_workflow_step_arguments(
        "csv_processor",
        {"operation": "read", "source_path": "sales.csv"},
        registry=registry,
    )
    assert out["file_path"] == "sales.csv"
    assert "source_path" not in out
    assert out["operation"] == "read"


def test_normalize_data_clean_operation_to_operations(registry: ToolRegistry) -> None:
    from leagent.tools.data.data_clean import DataCleanTool

    registry.register(DataCleanTool())
    out = normalize_workflow_step_arguments(
        "data_clean",
        {"operation": "remove_duplicates", "source_path": "data.csv"},
        registry=registry,
    )
    assert out["operations"] == [{"type": "remove_duplicates"}]
    assert "operation" not in out
    assert out["source_path"] == "data.csv"


def test_normalize_data_clean_when_operations_null(registry: ToolRegistry) -> None:
    from leagent.tools.data.data_clean import DataCleanTool

    registry.register(DataCleanTool())
    out = normalize_workflow_step_arguments(
        "clean",
        {"operation": "clean", "operations": None, "source_path": "data.csv"},
        registry=registry,
    )
    assert out["operations"] == [{"type": "remove_duplicates"}]
    assert "operation" not in out


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
