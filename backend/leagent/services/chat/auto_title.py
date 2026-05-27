"""Auto-generate short chat session titles from the first user–assistant exchange."""

from __future__ import annotations

import contextlib
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from leagent.exceptions.llm import LLMServiceError
from leagent.llm import ChatMessage
from leagent.llm import MessageRole as LLMMessageRole
from leagent.llm.base import LLMResponse
from leagent.llm.error_policy import classify_llm_error

if TYPE_CHECKING:
    from uuid import UUID

    from leagent.llm.service import LLMService
    from leagent.services.chat.service import ChatService

logger = logging.getLogger(__name__)

AUTO_CHAT_TITLE_META_KEY = "auto_chat_title_done"
AUTO_CHAT_TITLE_ATTEMPTED_KEY = "auto_chat_title_attempted"

_PLACEHOLDER_LOWER = frozenset(
    {
        "",
        "new chat",
        "新对话",
    },
)

# Server defaults: ``Chat …`` (stream auto-create), ``New Chat …`` (POST /sessions fallback).
_CHAT_DATETIME_NAME_RE = re.compile(
    r"^(?:Chat|New Chat) \d{4}-\d{2}-\d{2} \d{2}:\d{2}$",
    re.IGNORECASE,
)

# Title calls must not inherit chat-stream reasoning overrides or enable thinking
# (DeepSeek can burn the entire budget on reasoning_content and return empty content).
_TITLE_MAX_TOKENS = 128
_TITLE_LLM_KWARGS: dict[str, Any] = {
    "thinking": {"type": "disabled"},
    "enable_thinking": False,
}

_TITLE_SYSTEM_PROMPT = """You name chat threads for a sidebar list. Reply with a single short title only:
- Max 48 characters, one line, no quotation marks, no trailing punctuation like "." or "。"
- Use the same language as the user's message when it is clearly Chinese, English, or another language.
- Summarize the topic or intent; do not prefix with "Chat" or "对话"."""


def is_placeholder_session_name(name: str | None) -> bool:
    """True if the session still uses a generic/default title."""
    if name is None:
        return True
    stripped = name.strip()
    if not stripped:
        return True
    if stripped.lower() in _PLACEHOLDER_LOWER:
        return True
    return bool(_CHAT_DATETIME_NAME_RE.match(stripped))


def normalize_generated_title(raw: str) -> str | None:
    """Sanitize model output for persistence."""
    text = (raw or "").strip()
    text = text.strip(' "\'「」『』')
    text = re.sub(r"\s+", " ", text)
    if len(text) < 2:
        return None
    if len(text) > 80:
        text = text[:80].rstrip()
    if is_placeholder_session_name(text):
        return None
    return text


def _meta_title_done(raw: str | None) -> bool:
    if not raw:
        return False
    try:
        meta = json.loads(raw)
    except (TypeError, ValueError):
        return False
    if not isinstance(meta, dict):
        return False
    return bool(meta.get(AUTO_CHAT_TITLE_META_KEY))


@contextlib.asynccontextmanager
async def _isolated_title_llm_context():
    """Avoid inheriting per-request DeepSeek reasoning overrides from the chat stream."""
    try:
        from leagent.llm.providers.deepseek import (
            reset_reasoning_effort_override,
            set_reasoning_effort_override,
        )
    except Exception:
        yield
        return

    token = set_reasoning_effort_override("")
    try:
        yield
    finally:
        reset_reasoning_effort_override(token)


async def _complete_title_llm(
    llm: LLMService,
    messages: list[ChatMessage],
    *,
    provider: str | None = None,
    model: str | None = None,
) -> LLMResponse:
    """Complete title generation with the selected chat model when provided."""
    llm_kwargs = {
        "temperature": 0.2,
        "max_tokens": _TITLE_MAX_TOKENS,
        "tool_choice": "none",
        **_TITLE_LLM_KWARGS,
    }
    async with _isolated_title_llm_context():
        if provider and model:
            return await llm.complete(
                messages,
                provider=provider,
                model=model,
                **llm_kwargs,
            )

        last_exc: Exception | None = None
        for tier in ("tier2", "tier1"):
            try:
                return await llm.complete(
                    messages,
                    tier=tier,
                    **llm_kwargs,
                )
            except LLMServiceError as exc:
                last_exc = exc
                logger.debug("auto_title_llm_failed tier=%s", tier, exc_info=True)
            except Exception as exc:
                last_exc = exc
                logger.debug("auto_title_llm_unexpected tier=%s", tier, exc_info=True)
        if last_exc is not None:
            raise last_exc
        raise LLMServiceError("auto_title_llm_unavailable")


async def maybe_auto_title_session(
    chat_svc: ChatService,
    llm: LLMService,
    session_id: UUID,
    user_id: UUID,
    *,
    user_text: str,
    assistant_text: str,
    require_assistant_message: bool = True,
    model_provider: str | None = None,
    model_name: str | None = None,
) -> None:
    """If the session still has a placeholder name, set a concise LLM title once."""
    user_snip = (user_text or "").strip()
    assistant_snip = (assistant_text or "").strip()
    if not user_snip and not assistant_snip:
        return

    session = await chat_svc.get_session(session_id, user_id=user_id)
    if session is None:
        logger.info("auto_chat_title_skip session_id=%s reason=session_missing", session_id)
        return
    if _meta_title_done(session.session_metadata):
        logger.debug("auto_chat_title_skip session_id=%s reason=done", session_id)
        return
    if not is_placeholder_session_name(session.name):
        logger.debug("auto_chat_title_skip session_id=%s reason=custom_name", session_id)
        return
    min_messages = 2 if require_assistant_message else 1
    if session.message_count < min_messages:
        logger.info(
            "auto_chat_title_skip session_id=%s reason=message_count count=%s required=%s",
            session_id,
            session.message_count,
            min_messages,
        )
        return

    user_ctx = user_snip if user_snip else "(empty)"
    asst_ctx = assistant_snip[:1200] if assistant_snip else "(not available yet)"

    messages = [
        ChatMessage(role=LLMMessageRole.SYSTEM, content=_TITLE_SYSTEM_PROMPT),
        ChatMessage(
            role=LLMMessageRole.USER,
            content=f"User:\n{user_ctx}\n\nAssistant (excerpt):\n{asst_ctx}",
        ),
    ]

    async def _mark_attempted() -> None:
        if not require_assistant_message:
            return
        await chat_svc.merge_session_metadata(
            session_id,
            user_id,
            patch={AUTO_CHAT_TITLE_ATTEMPTED_KEY: True},
        )

    logger.info(
        "auto_chat_title_start session_id=%s provider=%s model=%s",
        session_id,
        model_provider,
        model_name,
    )
    try:
        response = await _complete_title_llm(
            llm,
            messages,
            provider=model_provider,
            model=model_name,
        )
    except LLMServiceError as exc:
        if not classify_llm_error(exc).retryable:
            await _mark_attempted()
        logger.warning(
            "auto_chat_title_llm_failed session_id=%s retryable=%s error=%s",
            session_id,
            classify_llm_error(exc).retryable,
            exc,
        )
        return
    except Exception:
        logger.warning("auto_chat_title_unexpected session_id=%s", session_id, exc_info=True)
        return

    title = normalize_generated_title(response.content or "")
    if not title:
        logger.warning(
            "auto_chat_title_invalid session_id=%s raw=%r",
            session_id,
            (response.content or "")[:120],
        )
        return

    updated = await chat_svc.update_session(session_id, user_id, name=title)
    if updated is None:
        await _mark_attempted()
        logger.warning("auto_chat_title_update_failed session_id=%s", session_id)
        return

    await chat_svc.merge_session_metadata(
        session_id,
        user_id,
        patch={
            AUTO_CHAT_TITLE_META_KEY: True,
            AUTO_CHAT_TITLE_ATTEMPTED_KEY: True,
        },
    )
    logger.info(
        "auto_chat_title_set session_id=%s title=%r provider=%s model=%s",
        session_id,
        title,
        model_provider,
        model_name,
    )
