"""Runtime profile budget resolution tests."""

from __future__ import annotations

from leagent.agent.runtime_profile import (
    resolve_chat_conversation_timeout_sec,
    resolve_runtime_budget,
    runtime_budget_tool_extra,
)


def test_coding_long_budget_is_one_hour() -> None:
    budget = resolve_runtime_budget("coding_long")
    assert budget.task_timeout_sec == 3600
    assert budget.conversation_timeout_sec == 3600
    assert budget.tool_timeout_sec == 1800


def test_coding_extended_budget_is_two_hours() -> None:
    budget = resolve_runtime_budget("coding_extended")
    assert budget.task_timeout_sec == 7200
    assert budget.conversation_timeout_sec == 7200
    assert budget.tool_timeout_sec == 3600


def test_chat_timeout_uses_coding_long_when_project_bound() -> None:
    timeout = resolve_chat_conversation_timeout_sec(project_path="/tmp/demo")
    assert timeout == 3600


def test_chat_timeout_honours_explicit_extended_profile() -> None:
    timeout = resolve_chat_conversation_timeout_sec(runtime_profile="coding_extended")
    assert timeout == 7200


def test_chat_timeout_standard_without_project() -> None:
    timeout = resolve_chat_conversation_timeout_sec()
    assert timeout == 600


def test_runtime_budget_tool_extra_carries_profile_name() -> None:
    extra = runtime_budget_tool_extra("coding_extended")
    assert extra["runtime_profile"] == "coding_extended"
    assert extra["runtime_budget"]["task_timeout_sec"] == 7200
