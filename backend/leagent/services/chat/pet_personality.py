"""Load the user's pet personality document from project settings.

The pet "personality" is a free-form document (e.g. "Miku, a playful cat
girlfriend who ends sentences with nya~") stored under the ``personality.document``
key inside the JSON ``settings`` blob on the most-recently-updated pet project.
It is injected into LLM-generated pet bubble greetings and the agent system
prompt so the desk-pet voice reflects the user's chosen character.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text

from leagent.services.database.sqlite_compat import (
    session_dialect_name,
    sqlite_parent_id_text,
)

if TYPE_CHECKING:
    from uuid import UUID

    from leagent.services.database import DatabaseService

logger = logging.getLogger(__name__)

# Cap the document at 2000 chars before injecting it into prompts to avoid
# bloating the system prompt or daily-greeting LLM call.
MAX_PERSONALITY_CHARS = 2000
_DEFAULT_PERSONALITY_PATH = (
    Path(__file__).resolve().parents[2]
    / "prompts"
    / "templates"
    / "default_pet_personality.md"
)


def get_default_pet_personality_document() -> str:
    """Load the managed default personality document from prompt templates."""
    try:
        return _DEFAULT_PERSONALITY_PATH.read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001 - missing defaults should not break the UI
        logger.debug("default_pet_personality_read_failed", exc_info=True)
        return ""


def _extract_personality_document(settings_raw: str | None) -> str | None:
    if not settings_raw:
        return None
    try:
        parsed = json.loads(settings_raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    persona = parsed.get("personality")
    if not isinstance(persona, dict):
        return None
    doc = persona.get("document")
    if not isinstance(doc, str):
        return None
    text_doc = doc.strip()
    if not text_doc:
        return None
    if len(text_doc) > MAX_PERSONALITY_CHARS:
        text_doc = text_doc[:MAX_PERSONALITY_CHARS].rstrip()
    return text_doc


async def get_active_pet_personality(
    db: "DatabaseService | None", user_id: "UUID | str | None"
) -> str | None:
    """Return the personality document for the user's most-recent pet project.

    Returns ``None`` if there is no project, no personality set, or any error
    occurs (this feature is best-effort and must never break the caller).
    """
    if db is None or user_id is None:
        return None
    try:
        async with db.session() as session:
            if session_dialect_name(session) == "sqlite":
                from uuid import UUID as _UUID

                uid = user_id if isinstance(user_id, _UUID) else _UUID(str(user_id))
                u_txt = await sqlite_parent_id_text(session, "users", uid)
                row = (
                    await session.execute(
                        text(
                            """
                            SELECT settings
                            FROM pet_projects
                            WHERE CAST(user_id AS TEXT) = :uid
                              AND is_deleted = 0
                              AND settings IS NOT NULL
                            ORDER BY updated_at DESC
                            LIMIT 1
                            """
                        ),
                        {"uid": u_txt},
                    )
                ).mappings().first()
                if row is None:
                    return None
                return _extract_personality_document(row.get("settings"))

            row = (
                await session.execute(
                    text(
                        """
                        SELECT settings
                        FROM pet_projects
                        WHERE user_id = :uid
                          AND is_deleted = false
                          AND settings IS NOT NULL
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """
                    ),
                    {"uid": str(user_id)},
                )
            ).mappings().first()
            if row is None:
                return None
            return _extract_personality_document(row.get("settings"))
    except Exception:  # noqa: BLE001
        logger.debug("get_active_pet_personality_failed", exc_info=True)
        return None


def build_pet_personality_addendum(personality: str | None) -> str:
    """Wrap the personality document for safe inclusion in the system prompt.

    Returns an empty string when no personality is set, so callers can
    unconditionally append the result to the existing system-prompt extra.
    """
    if not personality:
        return ""
    trimmed = personality.strip()
    if not trimmed:
        return ""
    if len(trimmed) > MAX_PERSONALITY_CHARS:
        trimmed = trimmed[:MAX_PERSONALITY_CHARS].rstrip()
    return (
        "## Pet Personality\n"
        "The user has defined the desk-pet's character below. When you call "
        "`emit_pet_bubble`, write the bubble line in this character's voice. "
        "This affects ONLY the pet bubble caption, not your main answer.\n\n"
        "<pet_personality>\n"
        f"{trimmed}\n"
        "</pet_personality>"
    )


async def apply_pet_personality_to_agent(
    agent: object | None,
    db: "DatabaseService | None",
    user_id: "UUID | str | None",
) -> None:
    """Best-effort: load personality and append it to ``agent.config.extra_system_prompt``.

    Safe to call when ``agent`` is ``None`` (no-op).
    """
    if agent is None:
        return
    personality = await get_active_pet_personality(db, user_id)
    addendum = build_pet_personality_addendum(personality)
    if not addendum:
        return
    try:
        cfg = getattr(agent, "config", None)
        if cfg is None:
            return
        existing = getattr(cfg, "extra_system_prompt", "") or ""
        merged = f"{existing}\n\n{addendum}" if existing.strip() else addendum
        cfg.extra_system_prompt = merged
    except Exception:  # noqa: BLE001
        logger.debug("apply_pet_personality_failed", exc_info=True)
