"""Tests for assistant message extension merging on /chat/stream persist."""

import json

from leagent.api.v1.chat import (
    _companion_sse_events,
    _merge_message_extensions_json,
    _openai_tool_call_from_stream_edata,
)


def test_openai_tool_call_from_stream_edata() -> None:
    raw = _openai_tool_call_from_stream_edata(
        {"id": "call_abc", "name": "search", "arguments": {"q": "x"}},
    )
    assert raw is not None
    assert raw["id"] == "call_abc"
    assert raw["type"] == "function"
    assert raw["function"]["name"] == "search"
    assert json.loads(raw["function"]["arguments"]) == {"q": "x"}


def test_merge_message_extensions_json_merges_workflow_and_ui() -> None:
    workflow = json.dumps({"chat_workflow": {"title": "T", "steps": []}, "chat_workflow_digest": "abc"})
    merged = _merge_message_extensions_json(
        workflow,
        thinking="step 1",
        task_progress=[{"task_id": "1", "label": "L", "status": "completed", "order": 0}],
        gen_ui={"tree": {"schemaVersion": "1"}, "tool_call_id": "tc1"},
        pet_bubble={"text": "Hi!", "emoji": "✨"},
    )
    assert merged is not None
    obj = json.loads(merged)
    assert obj["chat_workflow"]["title"] == "T"
    assert obj["thinking"] == "step 1"
    assert obj["task_progress"][0]["task_id"] == "1"
    assert obj["gen_ui"]["tool_call_id"] == "tc1"
    assert obj["pet_bubble"]["text"] == "Hi!"
    assert obj["pet_bubble"]["emoji"] == "✨"


def test_companion_sse_events_emit_pet_bubble() -> None:
    edata = {
        "success": True,
        "name": "emit_pet_bubble",
        "tool_call_id": "call_x",
        "data": {"success": True, "text": "Looking good", "emoji": "🐾"},
    }
    pairs = _companion_sse_events("tool_result", edata)
    assert ("pet_bubble", {"text": "Looking good", "emoji": "🐾"}) in pairs


def test_companion_sse_events_emit_pet_bubble_skips_empty_text() -> None:
    edata = {
        "success": True,
        "name": "emit_pet_bubble",
        "data": {"success": True, "text": "   "},
    }
    assert _companion_sse_events("tool_result", edata) == []
