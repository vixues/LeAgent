"""Auto-generate short chat session titles from the first user–assistant exchange."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from leagent.exceptions.llm import LLMServiceError
from leagent.llm import ChatMessage
from leagent.llm import MessageRole as LLMMessageRole

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


def _meta_title_attempted(raw: str | None) -> bool:
    if not raw:
        return False
    try:
        meta = json.loads(raw)
    except (TypeError, ValueError):
        return False
    if not isinstance(meta, dict):
        return False
    return bool(meta.get(AUTO_CHAT_TITLE_ATTEMPTED_KEY))


async def maybe_auto_title_session(
    chat_svc: ChatService,
    llm: LLMService,
    session_id: UUID,
    user_id: UUID,
    *,
    user_text: str,
    assistant_text: str,
    require_assistant_message: bool = True,
) -> None:
    """If the session still has a placeholder name, set a concise LLM title once."""
    user_snip = (user_text or "").strip()
    assistant_snip = (assistant_text or "").strip()
    if not user_snip and not assistant_snip:
        return

    session = await chat_svc.get_session(session_id, user_id=user_id)
    if session is None:
        return
    if _meta_title_done(session.session_metadata):
        return
    if _meta_title_attempted(session.session_metadata):
        return
    if not is_placeholder_session_name(session.name):
        return
    min_messages = 2 if require_assistant_message else 1
    if session.message_count < min_messages:
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

    try:
        response = await llm.complete(
            messages,
            tier="tier2",
            temperature=0.2,
            max_tokens=96,
            tool_choice="none",
        )
    except LLMServiceError:
        logger.debug("auto_title_llm_failed", exc_info=True)
        await _mark_attempted()
        return
    except Exception:
        logger.debug("auto_title_llm_unexpected", exc_info=True)
        await _mark_attempted()
        return

    title = normalize_generated_title(response.content or "")
    if not title:
        await _mark_attempted()
        return

    updated = await chat_svc.update_session(session_id, user_id, name=title)
    if updated is None:
        await _mark_attempted()
        return

    await chat_svc.merge_session_metadata(
        session_id,
        user_id,
        patch={
            AUTO_CHAT_TITLE_META_KEY: True,
            AUTO_CHAT_TITLE_ATTEMPTED_KEY: True,
        },
    )
    logger.info("auto_chat_title_set session_id=%s title_len=%s", session_id, len(title))
