"""Builtin skills on disk (shipped inside the LeAgent package).

This module only loads **skill directories** from ``leagent/skills/builtin/``.
It is unrelated to :mod:`leagent.skills.bundle_payload` (which **packs** a skill's
``SKILL.md`` + text resources into a prompt payload) and unrelated to
:mod:`leagent.skills.bundle_payload_cache` (LRU cache for that packing step).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from leagent.skills.base import Skill, SkillSource
from leagent.skills.loader import SkillLoader

BUILTIN_DIR = Path(__file__).parent / "builtin"

_bundled_skills: list[Skill] = []
_loaded: bool = False


def load_bundled_skills() -> list[Skill]:
    """Discover bundled skills synchronously.

    Returns a cached list on subsequent calls. Uses its own event loop
    when called outside an async context so callers (CLI commands) do
    not need to think about concurrency.
    """
    global _bundled_skills, _loaded
    if _loaded:
        return _bundled_skills

    loader = SkillLoader(BUILTIN_DIR, source=SkillSource.BUILTIN)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Callers that are already in an event loop should use
            # ``await loader.load_all()`` themselves; fall back to a
            # new loop for safety.
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(loader.load_all())
        finally:
            loop.close()
    else:
        loop.run_until_complete(loader.load_all())

    _bundled_skills = list(loader.loaded_skills.values())
    _loaded = True
    return _bundled_skills


def get_bundled_skills() -> list[Skill]:
    return load_bundled_skills()


def clear_bundled_skills() -> None:
    """Clear the cached bundled skills (testing hook)."""
    global _bundled_skills, _loaded
    _bundled_skills = []
    _loaded = False
