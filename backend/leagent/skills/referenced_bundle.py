"""Parse @skill chat tokens and build full skill bundles for system prompt injection.

Frontend sends tokens like ``@skill:Display_Label#skill-name`` (see ``buildSkillChatToken``).
When present in the user message, we force the same bundled payload as ``load_skill``
with ``include_bundled_content: true`` (resources + script sources within budget).

Formatting is delegated to :func:`~leagent.skills.bundle_payload.format_bundle_payload_markdown`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from leagent.skills.base import Skill
from leagent.skills.bundle_payload import (
    DEFAULT_MAX_PER_FILE_CHARS,
    DEFAULT_SKILL_BUNDLE_TOTAL_CHARS,
    build_bundle_payload,
    format_bundle_payload_markdown,
)

if TYPE_CHECKING:
    from leagent.skills.manager import SkillsManager

# Match ``@skill:anything#skill-id`` — id is kebab-case per Agent Skills name rules.
_SKILL_TOKEN_RE = re.compile(
    r"@skill:[^#\r\n]+#([a-z0-9]+(?:-[a-z0-9]+)*)",
    re.IGNORECASE,
)


def iter_skill_ids_from_message(text: str) -> list[str]:
    """Return unique skill manifest names from ``@skill:…#name`` tokens, in order of appearance."""
    seen: dict[str, None] = {}
    out: list[str] = []
    for m in _SKILL_TOKEN_RE.finditer(text or ""):
        sid = m.group(1).strip().lower()
        if sid and sid not in seen:
            seen[sid] = None
            out.append(sid)
    return out


def resolve_skill_by_token(manager: SkillsManager, token_skill_id: str) -> Skill | None:
    """Resolve skill like ``SkillTool``: exact name, then substring match on manifest name."""
    skill = manager.get_skill(token_skill_id)
    if skill:
        return skill
    lowered = token_skill_id.lower()
    return next((s for s in manager.all_skills if lowered in s.name.lower()), None)


def build_referenced_skills_append_extra(
    user_message: str,
    manager: SkillsManager | None,
    *,
    max_total_chars_per_skill: int = DEFAULT_SKILL_BUNDLE_TOTAL_CHARS,
) -> str:
    """Return markdown text to append to ``append_extra`` (turn_extras), or empty string."""
    if not manager or not (user_message or "").strip():
        return ""

    ids = iter_skill_ids_from_message(user_message)
    if not ids:
        return ""

    sections: list[str] = []
    for sid in ids:
        skill = resolve_skill_by_token(manager, sid)
        if skill is None:
            sections.append(
                f"### Referenced skill `{sid}`\n\n_(Skill not found — no bundle loaded.)_\n"
            )
            continue

        body = skill.read_body()
        if not body:
            body = skill.description

        body_out, bundle_extra = build_bundle_payload(
            skill,
            skill_body=body,
            max_total_chars=max_total_chars_per_skill,
            include_resources=True,
            include_scripts=True,
            max_per_file_chars=DEFAULT_MAX_PER_FILE_CHARS,
        )
        sections.append(
            format_bundle_payload_markdown(
                skill.name,
                body_out,
                bundle_extra,
                skill_section_title=(
                    f"### Skill `{skill.name}` (full bundle — referenced via @skill)"
                ),
            )
        )

    header = (
        "## Referenced Agent Skills\n"
        "The user referenced the following skill(s) with **@** — full bundled "
        "resources and script sources are inlined below (same as `load_skill` with "
        "bundled content).\n\n"
    )
    return header + "\n---\n\n".join(sections)
