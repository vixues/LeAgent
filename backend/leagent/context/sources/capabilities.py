"""Capabilities context source — advertises available tools and skills."""

from __future__ import annotations

import structlog

from leagent.context.sources import SOURCE_REGISTRY
from leagent.context.sources.base import ContextSource, ResolveContext
from leagent.context.types import ContextBlock, ContextScope, RenderTarget

logger = structlog.get_logger(__name__)


_CATEGORY_BUDGET_CHARS: dict[str, int] = {
    "canvas": 300,
    "gen": 400,
    "image": 200,
    "chart": 200,
    "code": 300,
    "doc": 600,
    "web": 300,
    "data": 200,
    "integration": 300,
    "util": 300,
    "workflow": 200,
    "skills": 500,
}

_DEFAULT_CATEGORY_BUDGET = 400

_ALWAYS_VISIBLE_TOOL_DESCRIPTIONS: dict[str, str] = {
    "config_file": (
        "Read/query JSON, YAML, and TOML configs directly, including "
        "`~/.openclaw/openclaw.json` for installed skill API keys; prefer this "
        "over code_execution for config reads."
    ),
    "markdown_processor": (
        "Markdown authoring toolkit: write/create/append markdown files, "
        "build from templates (story/report/article/meeting/readme/changelog), "
        "insert/replace/delete sections by heading, build tables and lists, "
        "merge files, generate TOC, format, convert to HTML/text. "
        "Always prefer this over code_execution for any .md file output."
    ),
    "text_processor": (
        "Text-file toolkit: write/append/prepend, regex find-and-replace, "
        "insert at line, transforms (uppercase/lowercase/wrap/indent/sort/"
        "unique/number_lines/dedent), extract by pattern/range/markers, "
        "split/join files, encoding detection. "
        "Always prefer this over code_execution for .txt file operations."
    ),
    "pdf_reader": (
        "PDF processor: extract text (full/by page), detect & extract tables, "
        "save embedded images, search text across pages, extract outline/bookmarks, "
        "convert pages to images, split/merge/extract pages, metadata. "
        "Always prefer this over code_execution for PDF operations."
    ),
    "image_ocr": (
        "Extract text from image files (PNG/JPG/WebP). Use when the user attaches "
        "images but the chat model is text-only."
    ),
    "code_execution": (
        "Run Python for data/code tasks. For image files on text-only models, use "
        "Pillow/OpenCV/imageio to read, resize, convert, or process images by path "
        "instead of expecting inline vision input."
    ),
    "get_genui_guide": (
        "GenUI guide: for non-trivial component UI, call this first for syntax/layout rules, "
        "then call list_ui_components before emit_ui_tree."
    ),
    "list_ui_components": (
        "GenUI component catalog: call after get_genui_guide and before non-trivial "
        "emit_ui_tree payloads to verify exact kind and prop names."
    ),
    "emit_ui_tree": (
        "Emit validated inline GenUI; for non-trivial trees, use get_genui_guide then "
        "list_ui_components before this tool."
    ),
    "todo_write": (
        "Session task list (Cursor-style): create/update in-chat todos with "
        "pending/in_progress/completed/cancelled. Use for multi-step plans, "
        "任务清单, and todo lists — not background jobs or export checklists."
    ),
    "todo_read": "Read the current session todo list.",
    "task_create": (
        "Background async job queue — creates queued worker tasks, not the in-chat todo list."
    ),
    "checklist_generator": (
        "Generate exportable checklist documents (markdown/PDF) — not live session todos."
    ),
}


class CapabilitiesSource:
    """Lists enabled tools and loaded skills for the LLM.

    Uses per-category character budgets to keep tool descriptions concise.
    Only the first sentence of each tool's description is included; detailed
    usage information is available on-demand via introspection tools
    (e.g. list_ui_components, get_genui_guide, get_html_canvas_guide).
    """

    id: str = "capabilities"
    kind: str = "identity"
    scope: ContextScope = ContextScope.SESSION
    priority: int = 1500
    weight: float = 1.0
    render_target: RenderTarget = RenderTarget.SYSTEM

    def invalidation_key(self, ctx: ResolveContext) -> str:
        return f"capabilities:{id(ctx.tools)}:{id(ctx.skills_manager)}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            tool_lines: list[str] = []
            skill_lines: list[str] = []

            if ctx.tools is not None:
                try:
                    deny_patterns = (
                        ctx.permission_context.always_deny_rules
                        if ctx.permission_context is not None
                        else None
                    )
                    if deny_patterns:
                        import fnmatch

                        enabled = [
                            t
                            for t in ctx.tools.get_enabled_tools()
                            if not any(fnmatch.fnmatch(t.name, p) for p in deny_patterns)
                        ]
                    else:
                        enabled = ctx.tools.get_enabled_tools()

                    category_chars: dict[str, int] = {}
                    emitted_tool_names: set[str] = set()
                    by_name = {getattr(tool, "name", ""): tool for tool in enabled}
                    for tool_name, desc in _ALWAYS_VISIBLE_TOOL_DESCRIPTIONS.items():
                        if tool_name in by_name:
                            tool_lines.append(f"- {tool_name}: {desc}")
                            emitted_tool_names.add(tool_name)

                    for tool in enabled:
                        tool_name = getattr(tool, "name", "")
                        if tool_name in emitted_tool_names:
                            continue
                        cat = getattr(tool, "category", None)
                        if cat is None:
                            cat_key = "util"
                        elif hasattr(cat, "value"):
                            cat_key = str(cat.value)
                        else:
                            cat_key = str(cat)
                        budget = _CATEGORY_BUDGET_CHARS.get(cat_key, _DEFAULT_CATEGORY_BUDGET)
                        current = category_chars.get(cat_key, 0)
                        if current >= budget:
                            continue

                        desc_raw = (getattr(tool, "description", "") or "")
                        short = _first_sentence(desc_raw)
                        line = f"- {tool_name}: {short}".rstrip()
                        category_chars[cat_key] = current + len(line)
                        tool_lines.append(line)
                except Exception:
                    logger.exception("capabilities_tools_failed")

            skills_mgr = ctx.skills_manager
            if skills_mgr is not None:
                try:
                    skills_attr = getattr(skills_mgr, "all_skills", None)
                    skills = skills_attr() if callable(skills_attr) else (skills_attr or [])
                    for skill in skills or []:
                        if getattr(skill, "enabled", True) is False:
                            continue
                        name = getattr(skill, "name", None)
                        if not name:
                            continue
                        desc_lines = (getattr(skill, "description", "") or "").strip().splitlines()
                        short = desc_lines[0] if desc_lines else ""
                        skill_lines.append(f"- {name}: {short}" if short else f"- {name}")
                except Exception:
                    logger.exception("capabilities_skills_failed")

            parts: list[str] = []
            if tool_lines:
                parts.append("Available tools:\n" + "\n".join(tool_lines))
            if skill_lines:
                parts.append(
                    "Available skills (call load_skill with name=<id>):\n"
                    + "\n".join(skill_lines)
                )

            body = "\n\n".join(parts)
            if not body.strip():
                return None

            return ContextBlock(
                source_id=self.id,
                kind=self.kind,
                render_target=self.render_target,
                body=body,
                tokens=ContextBlock.approx_tokens(body),
                cost=ContextBlock.approx_tokens(body),
                signature=ContextBlock.content_signature(self.id, body),
                priority=self.priority,
                weight=self.weight,
                metadata={
                    "tool_count": len(tool_lines),
                    "skill_count": len(skill_lines),
                },
            )
        except Exception:
            logger.exception("capabilities_resolve_failed")
            return None


def _first_sentence(text: str) -> str:
    """Extract the first sentence from a tool description for compact listing."""
    first_line = text.split("\n", 1)[0].strip()
    for sep in (". ", ".\t"):
        idx = first_line.find(sep)
        if idx > 0:
            return first_line[: idx + 1]
    return first_line[:120]


SOURCE_REGISTRY[CapabilitiesSource.id] = CapabilitiesSource
