"""ContextRecipe and recipe registry."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "RecipeEntry",
    "ContextRecipe",
    "RECIPE_REGISTRY",
    "get_recipe",
    "merge_recipes",
]


@dataclass(slots=True, frozen=True)
class RecipeEntry:
    source_id: str
    priority_override: int | None = None
    weight_override: float | None = None
    enabled: bool = True


@dataclass(slots=True, frozen=True)
class ContextRecipe:
    name: str
    entries: tuple[RecipeEntry, ...]
    max_chars: int = 24_000


def _recipe(name: str, source_ids: list[str]) -> ContextRecipe:
    return ContextRecipe(
        name=name,
        entries=tuple(RecipeEntry(source_id=sid) for sid in source_ids),
    )


RECIPE_REGISTRY: dict[str, ContextRecipe] = {
    "default_agent": _recipe(
        "default_agent",
        [
            "identity",
            "capabilities",
            "policies",
            "playbooks",
            "art_playbook",
            "canvas_guide",
            "chart_guide",
            "document_generation",
            "document_fonts",
            "email_tool",
            "settings_setup",
            "environment",
            "session_attachments",
            "session_artifacts",
            "active_project",
            "project_memory",
            "user_instructions",
            "recall",
            "working_set",
            "tool_history",
            "recent_reads",
        ],
    ),
    "script_agent": _recipe(
        "script_agent",
        [
            "identity",
            "capabilities",
            "policies",
            "playbooks",
            "art_playbook",
            "canvas_guide",
            "chart_guide",
            "document_generation",
            "document_fonts",
            "email_tool",
            "settings_setup",
            "environment",
            "working_set",
            "recent_reads",
            "tool_history",
        ],
    ),
    "coding_agent": _recipe(
        "coding_agent",
        [
            "identity",
            "capabilities",
            "policies",
            "playbooks",
            "art_playbook",
            "canvas_guide",
            "chart_guide",
            "document_generation",
            "document_fonts",
            "email_tool",
            "settings_setup",
            "environment",
            "session_artifacts",
            "active_project",
            "project_memory",
            "working_set",
            "recall",
            "tool_history",
            "recent_reads",
        ],
    ),
    "subagent": _recipe(
        "subagent",
        [
            "identity",
            "capabilities",
            "policies",
        ],
    ),
    "rule_judge": _recipe(
        "rule_judge",
        [
            "identity",
            "policies",
            "environment",
        ],
    ),
}


def get_recipe(name: str) -> ContextRecipe:
    """Look up a recipe by name, falling back to ``default_agent``."""
    return RECIPE_REGISTRY.get(name, RECIPE_REGISTRY["default_agent"])


def merge_recipes(base: ContextRecipe, extra: ContextRecipe) -> ContextRecipe:
    """Union of two recipes, preserving ``base`` order then appending new sources.

    Used for the monolithic coding session: when ``project_roots`` are bound,
    the parent (``default_agent``) turn absorbs the ``coding_agent`` recipe's
    sources instead of delegating to a child engine, so coding-specific
    context (project memory, playbooks, …) is assembled in-session.
    """
    seen = {e.source_id for e in base.entries}
    merged = list(base.entries) + [e for e in extra.entries if e.source_id not in seen]
    return ContextRecipe(
        name=f"{base.name}+{extra.name}",
        entries=tuple(merged),
        max_chars=max(base.max_chars, extra.max_chars),
    )
