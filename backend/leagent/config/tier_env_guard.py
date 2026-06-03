"""Detect deprecated environment variables (no side effects)."""

from __future__ import annotations

import re

_TIER_ENV_RE = re.compile(
    r"^(?:LEAGENT|WORKAGENT)_LLM__TIER[12]_|^LLM_TIER[12]_",
    re.IGNORECASE,
)

# Model selection moved to providers.yaml routing.tasks — not env vars.
_OBSOLETE_LLM_ENV_RE = re.compile(
    r"^(?:LEAGENT|WORKAGENT)_LLM__(?:DASHSCOPE|DEEPSEEK)_MODEL$",
    re.IGNORECASE,
)

# Entire WORKAGENT_LLM__ prefix is legacy; use provider keys + providers.yaml.
_WORKAGENT_LLM_RE = re.compile(r"^WORKAGENT_LLM__", re.IGNORECASE)


def detect_legacy_tier_env(environ: dict[str, str] | None = None) -> list[str]:
    """Return env var names that still use deprecated tier routing."""
    import os

    env = environ if environ is not None else os.environ
    return sorted(key for key in env if _TIER_ENV_RE.match(key))


def detect_obsolete_llm_env(environ: dict[str, str] | None = None) -> list[str]:
    """Return env vars that belong to removed tier/model env configuration."""
    import os

    env = environ if environ is not None else os.environ
    found: list[str] = []
    for key in env:
        if _WORKAGENT_LLM_RE.match(key):
            found.append(key)
            continue
        if _OBSOLETE_LLM_ENV_RE.match(key):
            found.append(key)
            continue
        if _TIER_ENV_RE.match(key):
            found.append(key)
    return sorted(set(found))
