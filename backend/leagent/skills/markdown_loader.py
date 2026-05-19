"""SKILL.md parser (v1.0 open spec).

This is a thin parser that turns a raw ``SKILL.md`` file into its
frontmatter dict and markdown body. Validation, directory scanning and
resource discovery live in :mod:`leagent.skills.loader`.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(?P<front>.*?)\n---\s*\n?(?P<body>.*)\Z", re.DOTALL)


def parse_skill_markdown(content: str) -> tuple[dict[str, Any], str]:
    """Parse a SKILL.md document into ``(frontmatter, body)``.

    Returns an empty dict + the raw content when the frontmatter is
    missing or malformed so callers can decide whether to reject the
    skill.
    """
    if not content.startswith("---"):
        return {}, content.strip()

    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content.strip()

    front_raw = match.group("front")
    body = match.group("body")

    try:
        frontmatter = yaml.safe_load(front_raw)
    except yaml.YAMLError:
        return {}, body.strip()

    if not isinstance(frontmatter, dict):
        return {}, body.strip()

    # Normalise both kebab-case and snake_case keys — the spec uses
    # ``allowed-tools`` but YAML authors often write ``allowed_tools``.
    normalised: dict[str, Any] = {}
    for key, value in frontmatter.items():
        if not isinstance(key, str):
            continue
        normalised[key.replace("-", "_")] = value

    return normalised, body.strip()
