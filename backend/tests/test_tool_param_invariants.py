"""Invariant tests for strict tool parameter contracts."""

from __future__ import annotations

import pytest

from leagent.tools.base import ToolContext, ToolResult
from leagent.tools.contract import validate_path_params_declared
from leagent.tools.doc.markdown_processor import MarkdownProcessorTool
from leagent.tools.registry import ToolRegistry


@pytest.fixture
def tool_context() -> ToolContext:
    return ToolContext(user_id="00000000-0000-0000-0000-000000000001", session_id=None)


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.discover_all()
    return reg


def test_path_params_declared_in_schema(registry: ToolRegistry) -> None:
    errors: list[str] = []
    for tool in registry.list_tools():
        errors.extend(
            validate_path_params_declared(
                tool_name=tool.name,
                schema=tool.parameters,
                path_params=tool.path_params,
                output_path_params=tool.output_path_params,
            )
        )
    assert not errors, "\n".join(errors)


def test_markdown_processor_rejects_path_alias() -> None:
    tool = MarkdownProcessorTool()
    valid, error = tool.validate_params(
        {"operation": "create", "path": "/tmp/x.md", "content": "# hi"}
    )
    assert not valid
    assert error is not None
    assert "file_path" in error


def test_markdown_processor_accepts_canonical_keys() -> None:
    tool = MarkdownProcessorTool()
    valid, error = tool.validate_params(
        {
            "operation": "create",
            "file_path": "/tmp/x.md",
            "content": "# hi",
        }
    )
    assert valid, error


@pytest.mark.asyncio
async def test_markdown_processor_wrong_key_fails_without_keyerror(
    tool_context: ToolContext,
) -> None:
    tool = MarkdownProcessorTool()
    result = await tool.run(
        {"operation": "create", "path": "/tmp/x.md", "content": "# hi"},
        tool_context,
    )
    assert isinstance(result, ToolResult)
    assert not result.success
    assert result.error is not None
    assert "file_path" in result.error


@pytest.mark.asyncio
async def test_markdown_processor_missing_file_path_fails_validation(
    tool_context: ToolContext,
) -> None:
    tool = MarkdownProcessorTool()
    result = await tool.run({"operation": "create", "content": "# hi"}, tool_context)
    assert not result.success
    assert result.error is not None
    assert "file_path" in result.error
