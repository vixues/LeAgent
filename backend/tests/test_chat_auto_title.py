"""Unit tests for chat session auto-title helpers."""

from leagent.services.chat.auto_title import (
    is_placeholder_session_name,
    normalize_generated_title,
)


def test_placeholder_session_names() -> None:
    assert is_placeholder_session_name(None) is True
    assert is_placeholder_session_name("") is True
    assert is_placeholder_session_name("   ") is True
    assert is_placeholder_session_name("New chat") is True
    assert is_placeholder_session_name("新对话") is True
    assert is_placeholder_session_name("Chat 2026-05-07 14:30") is True
    assert is_placeholder_session_name("New Chat 2026-05-07 14:30") is True
    assert is_placeholder_session_name("new chat 2026-05-07 14:30") is True
    assert is_placeholder_session_name("Redis cache tuning") is False


def test_normalize_generated_title() -> None:
    assert normalize_generated_title("") is None
    assert normalize_generated_title("  ") is None
    assert normalize_generated_title('"Docker compose tips"') == "Docker compose tips"
    assert normalize_generated_title("New chat") is None
