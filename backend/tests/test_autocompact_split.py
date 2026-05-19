"""Autocompact must not leave ``tool`` rows at the head of the kept tail."""

from __future__ import annotations

from leagent.memory.compact import snap_autocompact_split


def test_snap_autocompact_split_moves_before_tool_block() -> None:
    messages = [
        {"role": "user", "content": "u0"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "echo", "arguments": "{}"},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "{}"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "done"},
    ]
    raw_split = len(messages) - 3  # would start at index 2 = tool
    split = snap_autocompact_split(messages, raw_split)
    assert split == 1
    assert messages[split]["role"] == "assistant"
    tail = messages[split:]
    assert tail[0]["role"] == "assistant"
    assert any(m.get("role") == "tool" for m in tail)


def test_snap_autocompact_split_unchanged_when_tail_starts_with_user() -> None:
    messages = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ]
    split = snap_autocompact_split(messages, len(messages) - 2)
    assert split == 1
