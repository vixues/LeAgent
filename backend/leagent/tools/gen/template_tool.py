"""document_template — reusable, parameterized document/deck templates.

Agents turn a finished document into a template by parameterizing its
markdown (or slide list) with Jinja2 ``{{ variables }}`` and saving it under
a name. Later turns instantiate the template with fresh variable values and
render straight through the standard docgen pipeline — same themes, fonts,
tables, and layout engine as ``document_generate`` / ``slides_generate``.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

_ACTIONS = ("save", "list", "get", "delete", "preview", "generate")


class DocumentTemplateTool(SyncTool):
    """Save, inspect, preview, and instantiate docgen templates."""

    name = "document_template"
    description = (
        "Manage reusable document/deck templates for professional deliverables. "
        "`save` stores a template: markdown `content` (documents) or `slides` "
        "(decks) with Jinja2 {{variable}} placeholders, declared `variables` "
        "(name/description/default/required), a `theme` (built-in or one saved "
        "via theme_designer), and `defaults` (toc, cover, header/footer, "
        "aspect, ...). `generate` instantiates a saved template with variable "
        "values and renders PDF/DOCX/HTML/Markdown or PPTX through the "
        "standard pipeline. `preview` returns the rendered markdown/slides "
        "without writing a file; `list`/`get`/`delete` manage the store. Use "
        "templates to make recurring reports and branded decks repeatable and "
        "consistent."
    )
    category = ToolCategory.GEN
    version = "1.0.0"
    timeout_sec = 240
    aliases = ["template_save", "template_generate", "deck_template"]
    search_hint = (
        "template reusable document deck report 模板 复用 参数化 生成 "
        "placeholder variable jinja brand recurring"
    )
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 80_000
    output_path_params = ("output_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(_ACTIONS),
                    "description": (
                        "save: validate + store a template; generate: "
                        "instantiate + render to a file; preview: instantiate "
                        "without writing; list/get/delete: manage the store."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": (
                        "Template name (lowercase letters/digits/-/_). Required "
                        "for every action except list."
                    ),
                },
                "kind": {
                    "type": "string",
                    "enum": ["document", "deck"],
                    "description": "save: document (PDF/DOCX/HTML/MD) or deck (PPTX). Defaults to document.",
                },
                "description": {
                    "type": "string",
                    "description": "save: one-line description shown in list.",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "save (document kind): full markdown body with Jinja2 "
                        "placeholders — {{ variable }}, {% for %} loops, "
                        "{% if %} conditionals. Supports everything "
                        "document_generate supports (tables, ```chart fences, "
                        "callouts, [TOC], \\newpage)."
                    ),
                },
                "slides": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": (
                        "save (deck kind): slides_generate-shaped slide objects; "
                        "Jinja2 placeholders allowed in any text field (title, "
                        "kicker, body, takeaway, table cells, ...)."
                    ),
                },
                "theme": {
                    "type": "string",
                    "description": "save: theme name (built-in or saved via theme_designer).",
                },
                "variables": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "default": {},
                            "required": {"type": "boolean"},
                        },
                        "required": ["name"],
                    },
                    "description": "save: declared template variables.",
                },
                "defaults": {
                    "type": "object",
                    "description": (
                        "save: extra generation params applied at instantiation "
                        "— documents: toc, cover, numbered_headings, header, "
                        "footer, page, watermark; decks: aspect, footer_text, "
                        "show_slide_numbers, background, title, author."
                    ),
                },
                "values": {
                    "type": "object",
                    "description": "generate/preview: variable values for instantiation.",
                    "additionalProperties": {},
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "generate: bare filename for the rendered deliverable "
                        "(e.g. 'q3-report.pdf', 'deck.pptx'); placed in the "
                        "session workspace."
                    ),
                },
                "format": {
                    "type": "string",
                    "enum": ["pdf", "docx", "html", "markdown"],
                    "description": "generate (document kind): output format override.",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "save: replace an existing template (default true).",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        action = (params or {}).get("action", "")
        return f"Document template: {action}" if action else "Document template"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        from leagent.docgen import templates as store

        action = str(params.get("action") or "").strip().lower()
        if action not in _ACTIONS:
            raise ValueError(f"Unknown action: {action!r}. Use one of {_ACTIONS}.")

        if action == "list":
            return {"success": True, "templates": store.list_templates()}

        name = params.get("name")
        if not name:
            raise ValueError(f"`name` is required for action={action}.")

        if action == "save":
            template = store.DocTemplate.model_validate(
                {
                    "name": name,
                    "kind": params.get("kind") or "document",
                    "description": params.get("description"),
                    "theme": params.get("theme"),
                    "variables": params.get("variables") or [],
                    "content": params.get("content"),
                    "slides": params.get("slides"),
                    "defaults": params.get("defaults") or {},
                }
            )
            saved = store.save_template(
                template, overwrite=params.get("overwrite", True)
            )
            saved["success"] = True
            saved["usage"] = (
                f"Instantiate with action='generate', name='{saved['name']}', "
                "values={...}, output_path='...'."
            )
            return saved

        if action == "delete":
            removed = store.delete_template(str(name))
            return {"success": True, "deleted": removed, "name": name}

        template = store.load_template(str(name))
        if template is None:
            raise ValueError(f"Template not found: {name!r}")

        if action == "get":
            return {"success": True, "template": template.model_dump(exclude_none=True)}

        payload = store.render_template(template, params.get("values") or {})

        if action == "preview":
            return {"success": True, "name": template.name, "rendered": payload}

        # generate
        output_path = params.get("output_path")
        if not output_path:
            raise ValueError("`output_path` is required for action=generate.")
        payload.pop("kind", None)

        if template.kind == "deck":
            from leagent.tools.gen.slides_tool import SlidesGenerateTool

            gen_params = {**payload, "output_path": output_path}
            return SlidesGenerateTool().execute_sync(gen_params, context)

        from leagent.tools.gen.document_tool import DocumentGenerateTool

        gen_params = {**payload, "output_path": output_path}
        if params.get("format"):
            gen_params["format"] = params["format"]
        return DocumentGenerateTool().execute_sync(gen_params, context)
