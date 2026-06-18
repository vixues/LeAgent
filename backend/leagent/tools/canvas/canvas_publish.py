"""CanvasPublishTool — persist HTML / embed / gen-ui snapshots."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

_SESSION_ID_SENTINELS = frozenset(
    {"current", "this", "active", "default", "here", "same"},
)


def _resolve_session_uuid(raw: Any, context: ToolContext) -> UUID:
    """Use tool context when the model omits session_id or passes a placeholder string."""
    sid_raw: Any = raw if raw not in (None, "") else context.session_id
    if isinstance(sid_raw, str):
        s = sid_raw.strip().lower()
        if not s or s in _SESSION_ID_SENTINELS:
            sid_raw = context.session_id
    if not sid_raw:
        raise ValueError("session_id is required (no active session in tool context)")
    try:
        return UUID(str(sid_raw))
    except ValueError as e:
        raise ValueError("session_id must be a UUID or a known placeholder (e.g. 'current')") from e


class CanvasPublishTool(BaseTool):
    """Persist HTML / embed / gen-ui snapshot and return a signed preview path."""

    name = "canvas_publish"
    description = (
        "Publish a canvas document into the workspace canvas panel. "
        "Use this tool ONLY when the user explicitly asked for HTML / a webpage "
        "/ a printable report, or when the layout is genuinely page-scale and "
        "cannot be expressed by gen UI components. When GenUI is appropriate per "
        "`canvas_design` (charts, dashboards, poster/slide frames — not plain Q&A), prefer "
        "`emit_ui_tree`, which renders inline in the chat without opening the workspace. "
        "session_id: real chat UUID, or omit / pass 'current' to use the active "
        "session from context. "
        "mode=html: **inline the HTML directly in `html`** — the runtime "
        "auto-recovers malformed JSON and auto-stages large bodies when needed. "
        "Escape double quotes as \\\" and newlines as \\n. Keep image src URLs "
        "short: `/api/v1/files/{file_id}/preview` (omit JWT tokens). "
        "For multi-asset pages (HTML + CSS + JS) use "
        "`html_files` (map path → source) with `html_bundle_entry`; "
        "local <link>/<script> refs are inlined server-side. "
        "Inline `<script>` and `on*` handlers are stored but **off by default** "
        "in preview — the user enables JS from the Canvas preview toolbar. "
        "The host injects Tailwind, Inter, and shipped "
        "utility classes; call `get_html_canvas_guide` only when you need "
        "the reference template or exact class names. "
        "mode=embed_url: allowlisted iframe embeds (Google Maps, YouTube, "
        "Vimeo, OpenStreetMap). "
        "mode=gen_ui: persisted gen UI snapshot (rare; prefer `emit_ui_tree` "
        "for live inline rendering)."
    )
    category = ToolCategory.CANVAS
    aliases = ["webpage_write", "html_write"]
    is_read_only = False
    is_concurrency_safe = True
    search_hint = "html canvas preview publish maps embed"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["title", "mode"],
            "properties": {
                "title": {"type": "string", "minLength": 1, "maxLength": 500},
                "session_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Chat session UUID, or 'current' / 'this' / 'active' for the active session.",
                },
                "mode": {"type": "string", "enum": ["html", "embed_url", "gen_ui"]},
                "html": {
                    "type": "string",
                    "description": (
                        "Full HTML document for mode=html. Inline directly — the "
                        "runtime auto-recovers if JSON escaping breaks. Preferred "
                        "over `html_blob_id` for single-page documents."
                    ),
                },
                "html_blob_id": {
                    "type": "string",
                    "description": (
                        "For mode=html, finalized blob id from `tool_argument_blob`. "
                        "Fallback when a prior inline `html` call failed."
                    ),
                },
                "html_files": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": (
                        "For mode=html, relative path → file body (e.g. index.html, "
                        "assets/style.css). Mutually exclusive with `html` / `html_blob_id` / "
                        "`html_files_blob_id`. Large maps: put JSON in a finalized blob and "
                        "pass `html_files_blob_id`."
                    ),
                },
                "html_bundle_entry": {
                    "type": "string",
                    "description": "Entry file path inside `html_files` (default index.html).",
                },
                "html_files_blob_id": {
                    "type": "string",
                    "description": (
                        "Finalized UTF-8 JSON blob: {\"entry\":\"index.html\",\"files\":{...}} "
                        "same shape as `html_files` + `html_bundle_entry`."
                    ),
                },
                "embed_url": {"type": "string"},
                "ui_snapshot": {"type": "object"},
                "canvas_id": {"type": "string"},
                "message_id": {"type": "string"},
                "open_in_panel": {"type": "boolean", "default": True},
            },
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        from leagent.main import get_service_manager

        sm = get_service_manager()
        if sm.canvas is None:
            raise RuntimeError("Canvas service unavailable")
        if not context.user_id:
            raise ValueError("Missing user context")
        session_id = _resolve_session_uuid(params.get("session_id"), context)
        try:
            user_id = UUID(str(context.user_id))
        except ValueError as e:
            raise ValueError("Invalid user_id") from e

        cid = None
        if params.get("canvas_id"):
            try:
                cid = UUID(str(params["canvas_id"]))
            except ValueError as e:
                raise ValueError("Invalid canvas_id") from e
        mid = None
        if params.get("message_id"):
            try:
                mid = UUID(str(params["message_id"]))
            except ValueError as e:
                raise ValueError("Invalid message_id") from e

        mode = str(params["mode"])
        html_payload: str | None = params.get("html") if isinstance(params.get("html"), str) else None
        blob_raw = params.get("html_blob_id")
        has_blob = isinstance(blob_raw, str) and bool(blob_raw.strip())
        html_files: dict[str, str] | None = None
        raw_hf = params.get("html_files")
        if isinstance(raw_hf, dict) and raw_hf:
            html_files = {str(k): str(v) for k, v in raw_hf.items()}
        html_files_blob_raw = params.get("html_files_blob_id")
        has_files_blob = isinstance(html_files_blob_raw, str) and bool(html_files_blob_raw.strip())
        bundle_entry = params.get("html_bundle_entry")
        bundle_entry_s = str(bundle_entry).strip() if isinstance(bundle_entry, str) else None

        if mode == "html":
            has_inline = bool((html_payload or "").strip())
            has_files = bool(html_files)
            n_sources = sum([has_inline, has_blob, has_files, has_files_blob])
            if n_sources != 1:
                raise ValueError(
                    "For mode=html, pass exactly one of: `html`, `html_blob_id`, "
                    "`html_files`, or `html_files_blob_id`."
                )
            if has_blob:
                from leagent.tools.util.tool_argument_blob import resolve_blob_text

                try:
                    html_payload = await resolve_blob_text(context, str(blob_raw).strip())
                except ValueError as exc:
                    raise ValueError(str(exc)) from exc
            elif has_files_blob:
                from leagent.tools.util.tool_argument_blob import resolve_blob_text

                try:
                    raw_json = await resolve_blob_text(context, str(html_files_blob_raw).strip())
                except ValueError as exc:
                    raise ValueError(str(exc)) from exc
                try:
                    parsed = json.loads(raw_json)
                except json.JSONDecodeError as exc:
                    raise ValueError("html_files_blob_id must contain valid JSON") from exc
                if not isinstance(parsed, dict):
                    raise ValueError("html_files_blob_id JSON must be an object")
                files_obj = parsed.get("files")
                if not isinstance(files_obj, dict) or not files_obj:
                    raise ValueError('html_files_blob_id JSON must include non-empty "files" object')
                html_files = {str(k): str(v) for k, v in files_obj.items()}
                ent = parsed.get("entry")
                if isinstance(ent, str) and ent.strip():
                    bundle_entry_s = ent.strip()
                html_payload = None

        try:
            out = await sm.canvas.publish_revision(
                user_id=user_id,
                session_id=session_id,
                title=str(params["title"]),
                mode=mode,
                html=html_payload,
                html_files=html_files,
                html_bundle_entry=bundle_entry_s,
                embed_url=params.get("embed_url"),
                ui_snapshot=params.get("ui_snapshot"),
                message_id=mid,
                canvas_id=cid,
            )
        except PermissionError as e:
            raise ValueError(str(e)) from e

        return {
            **out,
            "open_in_panel": bool(params.get("open_in_panel", True)),
        }
