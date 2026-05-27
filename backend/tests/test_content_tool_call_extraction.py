"""Tests for recovering tool calls emitted as JSON in assistant content."""

from __future__ import annotations

from leagent.agent.deps import (
    _known_tool_names,
    _try_extract_content_tool_calls,
)


def test_extract_content_tool_call_from_json_blob() -> None:
    content = '\n\n{"name":"get_weather","arguments":{"city":"Beijing"}}'
    calls = _try_extract_content_tool_calls(
        content,
        known_tool_names={"get_weather"},
    )
    assert len(calls) == 1
    assert calls[0]["name"] == "get_weather"
    assert calls[0]["arguments"] == {"city": "Beijing"}


def test_extract_content_tool_call_ignores_unknown_tools() -> None:
    content = '{"name":"unknown_tool","arguments":{"x":1}}'
    assert _try_extract_content_tool_calls(content, known_tool_names={"get_weather"}) == []


def test_known_tool_names_from_openai_schema() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    assert _known_tool_names(tools) == {"get_weather"}
