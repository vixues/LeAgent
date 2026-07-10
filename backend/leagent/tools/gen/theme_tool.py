"""theme_designer — generate and manage custom docgen themes.

Derives a complete, contrast-safe theme from a brand seed (primary color,
mode, fonts), lints it against WCAG contrast rules, and persists it to the
custom theme store where ``document_generate`` / ``slides_generate`` resolve
it by name.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

_ACTIONS = ("create", "save", "list", "get", "delete")


class ThemeDesignerTool(SyncTool):
    """Create, inspect, and delete custom document/deck themes."""

    name = "theme_designer"
    description = (
        "Design and manage custom visual themes for document_generate and "
        "slides_generate. `create` derives a complete, contrast-checked theme "
        "from a brand seed (primary color + light/dark mode + optional accent "
        "and fonts) and saves it under a name; `save` stores an explicit theme "
        "payload (colors/fonts/sizes/spacing/deck overrides); `list`/`get`/"
        "`delete` manage the store. Saved themes resolve by name in the "
        "`theme` parameter of both generation tools and apply to PDF, DOCX, "
        "PPTX, and HTML output. Every save reports WCAG contrast lint "
        "warnings — fix them before shipping a deliverable."
    )
    category = ToolCategory.GEN
    version = "1.0.0"
    timeout_sec = 30
    aliases = ["theme_create", "theme_generate", "create_theme"]
    search_hint = (
        "theme design brand color palette customize style 主题 配色 品牌色 "
        "定制 document deck contrast fonts"
    )
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(_ACTIONS),
                    "description": (
                        "create: derive from a brand seed and save; save: store "
                        "an explicit payload; list/get/delete: manage themes."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": (
                        "Theme name (lowercase letters/digits/-/_). Required for "
                        "create/save/get/delete. Built-in names are protected."
                    ),
                },
                "kind": {
                    "type": "string",
                    "enum": ["document", "deck"],
                    "description": (
                        "What the theme targets: document (PDF/DOCX/HTML) or "
                        "deck (PPTX). Defaults to document."
                    ),
                },
                "primary": {
                    "type": "string",
                    "description": "Brand primary color '#RRGGBB' (create).",
                },
                "accent": {
                    "type": "string",
                    "description": "Accent color '#RRGGBB'; derived from primary when omitted (create).",
                },
                "mode": {
                    "type": "string",
                    "enum": ["light", "dark"],
                    "description": "Light or dark scheme (create; dark is typical for executive decks).",
                },
                "heading_font": {"type": "string", "description": "Heading font name (create)."},
                "body_font": {"type": "string", "description": "Body font name (create)."},
                "east_asia_font": {
                    "type": "string",
                    "description": "East-Asian font for Office formats, e.g. 'Microsoft YaHei' (create).",
                },
                "overrides": {
                    "type": "object",
                    "description": (
                        "Partial theme payload deep-merged over the derived "
                        "theme (create) — e.g. {\"sizes\": {\"body\": 11}, "
                        "\"colors\": {\"accent\": \"#00B8A9\"}}."
                    ),
                },
                "payload": {
                    "type": "object",
                    "description": (
                        "Full/partial theme payload for action=save: {colors "
                        "{primary,secondary,accent,text,text_light,background,"
                        "surface,border}, fonts {heading,body,mono,east_asia}, "
                        "sizes {title,h1,h2,h3,body,small,code}, spacing "
                        "{line_spacing,paragraph_spacing}, deck {dark,"
                        "title_size,slide_title_size,body_size}, zebra_tables}. "
                        "Missing fields inherit from the kind's base theme."
                    ),
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "create/save: return the derived payload + lint without persisting.",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        action = (params or {}).get("action", "")
        return f"Theme designer: {action}" if action else "Theme designer"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        from leagent.docgen import theming
        from leagent.docgen.themes import BUILTIN_THEMES, get_theme

        action = str(params.get("action") or "").strip().lower()
        if action not in _ACTIONS:
            raise ValueError(f"Unknown action: {action!r}. Use one of {_ACTIONS}.")
        kind = params.get("kind") or "document"
        name = params.get("name")

        if action == "list":
            builtin = [
                {"name": t.name, "kind": t.kind, "builtin": True}
                for t in BUILTIN_THEMES.values()
            ]
            custom = [
                {**item, "builtin": False} for item in theming.list_custom_themes()
            ]
            return {"success": True, "themes": builtin + custom}

        if not name:
            raise ValueError(f"`name` is required for action={action}.")

        if action == "get":
            resolved = get_theme(str(name), kind=kind)
            payload = theming.load_custom_theme_payload(str(name))
            return {
                "success": True,
                "name": resolved.name,
                "builtin": str(name) in BUILTIN_THEMES,
                "payload": payload,
                "resolved": resolved.model_dump(),
                "lint_warnings": theming.lint_theme(resolved),
            }

        if action == "delete":
            removed = theming.delete_custom_theme(str(name))
            return {"success": True, "deleted": removed, "name": name}

        if action == "create":
            primary = params.get("primary")
            if not primary:
                raise ValueError("`primary` (brand color '#RRGGBB') is required for create.")
            payload = theming.derive_theme_payload(
                kind=kind,
                primary=str(primary),
                accent=params.get("accent"),
                mode=params.get("mode"),
                heading_font=params.get("heading_font"),
                body_font=params.get("body_font"),
                east_asia_font=params.get("east_asia_font"),
            )
            overrides = params.get("overrides")
            if isinstance(overrides, dict) and overrides:
                _deep_merge(payload, overrides)
        else:  # save
            payload = params.get("payload")
            if not isinstance(payload, dict) or not payload:
                raise ValueError("`payload` (theme object) is required for save.")

        resolved = get_theme({**payload, "name": "candidate"}, kind=kind)
        if resolved.name != "candidate":
            raise ValueError("Theme payload failed validation against the theme schema.")
        lint = theming.lint_theme(resolved)
        result: dict[str, Any] = {
            "success": True,
            "name": name,
            "kind": kind,
            "payload": payload,
            "colors": resolved.colors.model_dump(),
            "lint_warnings": lint,
        }
        if params.get("dry_run"):
            result["saved"] = False
            return result

        saved = theming.save_custom_theme(str(name), payload, kind=kind)
        result.update({"saved": True, "path": saved["path"]})
        result["usage"] = (
            f'Pass theme: "{saved["name"]}" to '
            + ("slides_generate" if kind == "deck" else "document_generate")
            + "."
        )
        return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
