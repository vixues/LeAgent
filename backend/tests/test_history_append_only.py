"""Assert that the query loop never rewrites already-sent history in place.

Codex context rule: messages are append-only (or replaced wholesale by
compaction). Mid-turn steer / tool results must append, never mutate
prior OpenAI-shaped messages.
"""

from __future__ import annotations

import copy

from leagent.agent.query import SteerMessage, ToolResultMessage


def test_steer_to_openai_is_append_shape():
    msg = SteerMessage(content="focus on tests")
    assert msg.to_openai() == {"role": "user", "content": "focus on tests"}


def test_tool_result_to_openai_is_append_shape():
    msg = ToolResultMessage(
        tool_call_id="c1", name="project_read", content="ok", success=True,
    )
    assert msg.to_openai()["role"] == "tool"
    assert msg.to_openai()["tool_call_id"] == "c1"


def test_history_append_only_simulation():
    """Simulate a turn: assistant → tools → steer; prior rows stay byte-identical."""
    history: list[dict] = [
        {"role": "user", "content": "fix the bug"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "project_read", "arguments": "{}"},
                }
            ],
        },
    ]
    snapshot = copy.deepcopy(history)

    history.append(
        ToolResultMessage(
            tool_call_id="c1", name="project_read", content="file",
        ).to_openai()
    )
    history.append(SteerMessage(content="also run tests").to_openai())

    assert history[:2] == snapshot
    assert len(history) == 4
    assert history[2]["role"] == "tool"
    assert history[3] == {"role": "user", "content": "also run tests"}
