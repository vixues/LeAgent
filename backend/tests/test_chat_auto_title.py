"""Unit tests for chat session auto-title helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from leagent.exceptions.llm import LLMServiceError
from leagent.llm.base import LLMResponse
from leagent.services.chat.auto_title import (
    _complete_title_llm,
    is_placeholder_session_name,
    maybe_auto_title_session,
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


@pytest.mark.asyncio
async def test_complete_title_llm_falls_back_to_tier1() -> None:
    llm = MagicMock()
    llm.complete = AsyncMock(
        side_effect=[
            LLMServiceError("tier2 down"),
            LLMResponse(content="Redis 配置", model="m"),
        ]
    )
    result = await _complete_title_llm(llm, [])
    assert result.content == "Redis 配置"
    assert llm.complete.await_count == 2
    assert llm.complete.await_args_list[0].kwargs["tier"] == "tier2"
    assert llm.complete.await_args_list[1].kwargs["tier"] == "tier1"


@pytest.mark.asyncio
async def test_complete_title_llm_uses_selected_provider_model() -> None:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=LLMResponse(content="DeepSeek 标题", model="deepseek-chat"))

    result = await _complete_title_llm(
        llm,
        [],
        provider="deepseek",
        model="deepseek-chat",
    )

    assert result.content == "DeepSeek 标题"
    llm.complete.assert_awaited_once()
    kwargs = llm.complete.await_args.kwargs
    assert kwargs["provider"] == "deepseek"
    assert kwargs["model"] == "deepseek-chat"
    assert kwargs["thinking"] == {"type": "disabled"}
    assert kwargs["enable_thinking"] is False
    assert kwargs["max_tokens"] == 128
    assert "tier" not in kwargs


@pytest.mark.asyncio
async def test_maybe_auto_title_does_not_mark_attempted_on_retryable_error() -> None:
    session_id = uuid4()
    user_id = uuid4()
    chat_svc = MagicMock()
    chat_svc.get_session = AsyncMock(
        return_value=SimpleNamespace(
            session_metadata=None,
            name="Chat 2026-05-07 14:30",
            message_count=2,
        )
    )
    chat_svc.merge_session_metadata = AsyncMock()
    chat_svc.update_session = AsyncMock()
    llm = MagicMock()
    llm.complete = AsyncMock(side_effect=LLMServiceError("network: disconnected"))

    await maybe_auto_title_session(
        chat_svc,
        llm,
        session_id,
        user_id,
        user_text="hello",
        assistant_text="world",
    )

    chat_svc.merge_session_metadata.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_auto_title_retries_after_previous_attempt() -> None:
    session_id = uuid4()
    user_id = uuid4()
    chat_svc = MagicMock()
    chat_svc.get_session = AsyncMock(
        return_value=SimpleNamespace(
            session_metadata='{"auto_chat_title_attempted": true}',
            name="新对话",
            message_count=2,
        )
    )
    chat_svc.update_session = AsyncMock(return_value=SimpleNamespace(id=session_id))
    chat_svc.merge_session_metadata = AsyncMock()
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=LLMResponse(content="LeAgent 快速上手", model="m"))

    await maybe_auto_title_session(
        chat_svc,
        llm,
        session_id,
        user_id,
        user_text="介绍 LeAgent",
        assistant_text="LeAgent 可以帮助你处理知识库、工作流和文件。",
    )

    chat_svc.update_session.assert_awaited_once_with(
        session_id,
        user_id,
        name="LeAgent 快速上手",
    )
