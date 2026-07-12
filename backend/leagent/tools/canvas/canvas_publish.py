"""CanvasPublishTool — persist HTML / embed / gen-ui snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from leagent.file.primitives import is_path_inside
from leagent.tools.base import BaseTool, ToolCategory, ToolContext

_SESSION_ID_SENTINELS = frozenset(
    {"current", "this", "active", "default", "here", "same"},
)
_COMPACT_PAYLOAD_BYTES = 20_480
_MAX_HTML_PATHS = 40


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


def _canvas_search_roots(context: ToolContext) -> list[Path]:
    """Roots allowed for ``html_paths`` resolution (project + session uploads)."""
    roots: list[Path] = []
    extra = context.extra or {}
    raw_roots = extra.get("project_roots")
    if isinstance(raw_roots, (list, tuple)):
        for item in raw_roots:
            try:
                roots.append(Path(str(item)).expanduser().resolve())
            except OSError:
                continue
    for key in ("project_root", "cwd"):
        val = extra.get(key)
        if isinstance(val, str) and val.strip():
            try:
                roots.append(Path(val).expanduser().resolve())
            except OSError:
                continue
    sid = context.session_id
    if sid:
        try:
            from leagent.services.session.paths import get_session_path_registry

            roots.append(get_session_path_registry().ensure_uploads_dir(sid))
        except Exception:  # noqa: BLE001
            pass
    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        if root.is_dir():
            out.append(root)
    return out


def _norm_rel_key(path: str) -> str:
    s = (path or "").strip().replace("\\", "/")
    if not s or s.startswith(("http://", "https://", "//", "data:", "blob:")):
        raise ValueError(f"Invalid html_paths entry: {path!r}")
    while s.startswith("./"):
        s = s[2:]
    if s.startswith("..") or "/../" in f"/{s}/":
        raise ValueError(f"Unsafe html_paths entry: {path!r}")
    return s.lstrip("/")


def load_html_paths_map(
    paths: list[str],
    context: ToolContext,
) -> dict[str, str]:
    """Read workspace/session files into an ``html_files`` map (thin publish path)."""
    if not paths:
        raise ValueError("html_paths must be a non-empty list of relative paths")
    if len(paths) > _MAX_HTML_PATHS:
        raise ValueError(f"html_paths: at most {_MAX_HTML_PATHS} paths allowed")
    roots = _canvas_search_roots(context)
    if not roots:
        raise ValueError(
            "html_paths requires an active coding project or session uploads directory"
        )
    files: dict[str, str] = {}
    for raw in paths:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("html_paths entries must be non-empty strings")
        key = _norm_rel_key(raw)
        found: Path | None = None
        candidate = Path(raw).expanduser()
        if candidate.is_absolute():
            resolved = candidate.resolve()
            if not is_path_inside(resolved, roots):
                raise ValueError(f"html_paths entry outside allowed roots: {raw!r}")
            if resolved.is_file():
                found = resolved
        else:
            for root in roots:
                resolved = (root / key).resolve()
                if not is_path_inside(resolved, [root]):
                    continue
                if resolved.is_file():
                    found = resolved
                    break
        if found is None:
            raise ValueError(
                f"html_paths file not found under project/session roots: {key!r}"
            )
        try:
            files[key] = found.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"html_paths[{key!r}] must be UTF-8 text") from exc
    return files


def _payload_byte_size(html_files: dict[str, str] | None, html: str | None) -> int:
    total = 0
    if isinstance(html, str):
        total += len(html.encode("utf-8"))
    if isinstance(html_files, dict):
        for k, v in html_files.items():
            total += len(str(k).encode("utf-8")) + len(str(v).encode("utf-8"))
    return total


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
        "mode=html payload ladder (avoid output-token truncation): "
        "(1) compact single page ≲ ~20KB → inline `html`; "
        "(2) larger pages → write files with `project_write` / session tools, then "
        "`html_paths` + `html_bundle_entry` (thin call — bodies read from disk); "
        "(3) or stage JSON via `tool_argument_blob` → `html_files_blob_id` / `html_blob_id`; "
        "(4) inline `html_files` map only when the TOTAL map stays under ~20KB. "
        "Never put a multi-hundred-KB page into one tool-call JSON string. "
        "Escape double quotes as \\\" and newlines as \\n when inlining. Keep image "
        "src URLs short: `/api/v1/files/{file_id}/preview` (omit JWT tokens). "
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
                    "description": (
                        "Chat session UUID, or 'current' / 'this' / 'active' "
                        "for the active session."
                    ),
                },
                "mode": {"type": "string", "enum": ["html", "embed_url", "gen_ui"]},
                "html": {
                    "type": "string",
                    "description": (
                        "Full HTML document for mode=html when ≲ ~20KB. "
                        "Larger pages: prefer `html_paths` or `html_files_blob_id`."
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
                        "For mode=html, relative path → file body. Only when the TOTAL "
                        "map is ≲ ~20KB. Larger maps: use `html_paths` (disk) or "
                        "`html_files_blob_id`. Mutually exclusive with other html sources."
                    ),
                },
                "html_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": _MAX_HTML_PATHS,
                    "description": (
                        "For mode=html: relative paths under the active coding project "
                        "or session uploads directory. Bodies are read from disk — "
                        "preferred for large pages after `project_write` / file writes. "
                        "Use with `html_bundle_entry` (default index.html)."
                    ),
                },
                "html_bundle_entry": {
                    "type": "string",
                    "description": (
                        "Entry file path inside `html_files` / `html_paths` "
                        "(default index.html)."
                    ),
                },
                "html_files_blob_id": {
                    "type": "string",
                    "description": (
                        "Finalized UTF-8 JSON blob: "
                        '{"entry":"index.html","files":{...}} '
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
        html_payload: str | None = (
            params.get("html") if isinstance(params.get("html"), str) else None
        )
        blob_raw = params.get("html_blob_id")
        has_blob = isinstance(blob_raw, str) and bool(blob_raw.strip())
        html_files: dict[str, str] | None = None
        raw_hf = params.get("html_files")
        if isinstance(raw_hf, dict) and raw_hf:
            html_files = {str(k): str(v) for k, v in raw_hf.items()}
        html_files_blob_raw = params.get("html_files_blob_id")
        has_files_blob = isinstance(html_files_blob_raw, str) and bool(
            html_files_blob_raw.strip()
        )
        raw_paths = params.get("html_paths")
        html_paths_list: list[str] | None = None
        if isinstance(raw_paths, list) and raw_paths:
            html_paths_list = [str(p) for p in raw_paths]
        has_paths = bool(html_paths_list)
        bundle_entry = params.get("html_bundle_entry")
        bundle_entry_s = (
            str(bundle_entry).strip() if isinstance(bundle_entry, str) else None
        )

        if mode == "html":
            has_inline = bool((html_payload or "").strip())
            has_files = bool(html_files)
            n_sources = sum(
                [has_inline, has_blob, has_files, has_files_blob, has_paths]
            )
            if n_sources != 1:
                raise ValueError(
                    "For mode=html, pass exactly one of: `html`, `html_blob_id`, "
                    "`html_files`, `html_files_blob_id`, or `html_paths`."
                )
            force_shard = bool((context.extra or {}).get("force_sharded_html"))
            oversized_map = (
                has_files
                and _payload_byte_size(html_files, None) > _COMPACT_PAYLOAD_BYTES
            )
            # After repeated output-length recovery, refuse giant inline bodies /
            # maps so the model must use disk paths or blob staging.
            if force_shard and (has_inline or oversized_map):
                raise ValueError(
                    "Large inline HTML payloads are blocked after output-length "
                    "truncation. Write files to the project/session workspace, then "
                    "call `canvas_publish` with `html_paths` + `html_bundle_entry`, "
                    "or stage via `tool_argument_blob` → `html_files_blob_id` / "
                    "`html_blob_id`. Do not re-emit the full page in one tool call."
                )
            if has_paths:
                assert html_paths_list is not None
                html_files = load_html_paths_map(html_paths_list, context)
                html_payload = None
            elif has_blob:
                from leagent.tools.util.tool_argument_blob import resolve_blob_text

                try:
                    html_payload = await resolve_blob_text(
                        context, str(blob_raw).strip()
                    )
                except ValueError as exc:
                    raise ValueError(str(exc)) from exc
            elif has_files_blob:
                from leagent.tools.util.tool_argument_blob import resolve_blob_text

                try:
                    raw_json = await resolve_blob_text(
                        context, str(html_files_blob_raw).strip()
                    )
                except ValueError as exc:
                    raise ValueError(str(exc)) from exc
                try:
                    parsed = json.loads(raw_json)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "html_files_blob_id must contain valid JSON"
                    ) from exc
                if not isinstance(parsed, dict):
                    raise ValueError("html_files_blob_id JSON must be an object")
                files_obj = parsed.get("files")
                if not isinstance(files_obj, dict) or not files_obj:
                    raise ValueError(
                        'html_files_blob_id JSON must include non-empty "files" object'
                    )
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
