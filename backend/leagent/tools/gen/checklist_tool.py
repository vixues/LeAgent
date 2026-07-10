"""checklist_generate — status-tracked checklists in the docgen subsystem.

Restores and generalises the legacy ``checklist_generator`` tool on top of the
unified ``docgen`` stack: grouped or flat items with per-item status,
priority, assignee, due date, notes and nested sub-items; a progress summary
and status legend; and export to Markdown, JSON, HTML, PDF, or DOCX with the
same professional themes as ``document_generate``. Sources: manual input, a
workflow definition, or a rules file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from leagent.docgen.checklist import build_checklist_block, checklist_to_dict
from leagent.docgen.model import DocumentSpec
from leagent.docgen.themes import list_theme_names
from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

_EXT_FORMATS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".html": "html",
    ".htm": "html",
    ".md": "markdown",
    ".markdown": "markdown",
    ".json": "json",
}
_FORMAT_EXTS = {
    "pdf": ".pdf",
    "docx": ".docx",
    "html": ".html",
    "markdown": ".md",
    "json": ".json",
}

_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "text": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["pending", "in_progress", "completed", "blocked", "skipped"],
        },
        "priority": {
            "type": "string",
            "enum": ["low", "medium", "high", "critical"],
        },
        "due_date": {"type": "string"},
        "assignee": {"type": "string"},
        "notes": {"type": "string"},
        "sub_items": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["text"],
}


class ChecklistGeneratorTool(SyncTool):
    """Generate status-tracked checklists (Markdown/JSON/HTML/PDF/DOCX)."""

    name = "checklist_generate"
    description = (
        "Generate a status-tracked checklist and export it to Markdown, JSON, "
        "HTML, PDF, or DOCX. Supports grouped or flat items with per-item "
        "status (pending/in_progress/completed/blocked/skipped), priority "
        "(low/medium/high/critical), assignee, due date, notes, and nested "
        "sub-items, plus an automatic progress summary and status legend. "
        "Build from manual items/groups, or from a workflow definition or "
        "rules file (source_type). Rendered with the same professional docgen "
        "themes; CJK/Chinese text is always font-safe."
    )
    category = ToolCategory.GEN
    version = "2.0.0"
    timeout_sec = 120
    aliases = [
        "checklist_generator",
        "checklist",
        "todo_gen",
        "task_list_gen",
        "create_checklist",
    ]
    search_hint = (
        "checklist todo task list 清单 检查表 待办 status priority progress "
        "export markdown json html pdf docx workflow rules"
    )
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000
    path_params = ("source_path",)
    output_path_params = ("output_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        themes = list_theme_names(kind="document")
        return {
            "type": "object",
            "properties": {
                "output_path": {
                    "type": "string",
                    "description": (
                        "Bare filename for the checklist (e.g. 'launch.md', "
                        "'qa.pdf', 'tasks.json'); placed in the session "
                        "workspace. The extension selects the format unless "
                        "`format` is set."
                    ),
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "json", "html", "pdf", "docx"],
                    "description": "Output format. Defaults to the extension, else markdown.",
                },
                "title": {"type": "string", "description": "Checklist title."},
                "description": {"type": "string", "description": "Checklist description."},
                "source_type": {
                    "type": "string",
                    "enum": ["manual", "workflow", "rules"],
                    "description": (
                        "Where items come from. 'manual' (default) uses `groups`/"
                        "`items`; 'workflow'/'rules' parse `source_path`."
                    ),
                },
                "source_path": {
                    "type": "string",
                    "description": "Path to a workflow or rules file (YAML/JSON) for those sources.",
                },
                "groups": {
                    "type": "array",
                    "description": "Grouped items: [{name, description, items:[…]}].",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "items": {"type": "array", "items": _ITEM_SCHEMA},
                        },
                        "required": ["items"],
                    },
                },
                "items": {
                    "type": "array",
                    "description": "Flat list of items (alternative to `groups`).",
                    "items": _ITEM_SCHEMA,
                },
                "include_progress": {
                    "type": "boolean",
                    "description": "Show the progress summary + bar. Defaults to true.",
                },
                "include_legend": {
                    "type": "boolean",
                    "description": "Show the status legend. Defaults to true.",
                },
                "theme": {
                    "type": "string",
                    "description": f"Visual theme for HTML/PDF/DOCX. Built-ins: {', '.join(themes)}.",
                },
            },
            "required": ["output_path"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Generating checklist"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        output_path = Path(params["output_path"])
        fmt = (params.get("format") or params.get("output_format") or "").strip().lower()
        if not fmt:
            fmt = _EXT_FORMATS.get(output_path.suffix.lower(), "markdown")
        if fmt not in _FORMAT_EXTS:
            raise ValueError(f"Unsupported format: {fmt}")
        if _EXT_FORMATS.get(output_path.suffix.lower()) != fmt:
            output_path = output_path.with_suffix(_FORMAT_EXTS[fmt])

        block = build_checklist_block(params)
        if not block.normalized_groups() or not any(
            g.items for g in block.normalized_groups()
        ):
            raise ValueError(
                "Checklist is empty — provide `items`, `groups`, or a valid "
                "`source_path` for workflow/rules sources."
            )

        logger.info(
            "checklist_generate_start",
            output_path=str(output_path),
            format=fmt,
            source=params.get("source_type", "manual"),
        )

        if fmt == "json":
            payload = checklist_to_dict(block)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return {
                "success": True,
                "output_path": str(output_path),
                "format": "json",
                "content_stats": payload["stats"],
                "warnings": [],
            }

        spec = DocumentSpec.model_validate(
            {
                "title": block.title or params.get("title") or "Checklist",
                "theme": params.get("theme") or "professional",
                "blocks": [block],
            }
        )
        if fmt == "pdf":
            from leagent.docgen.renderers.pdf import render_pdf

            return render_pdf(spec, output_path)
        if fmt == "docx":
            from leagent.docgen.renderers.docx import render_docx

            return render_docx(spec, output_path)
        if fmt == "html":
            from leagent.docgen.renderers.html import render_html

            return render_html(spec, output_path)
        from leagent.docgen.renderers.html import render_markdown

        return render_markdown(spec, output_path)
