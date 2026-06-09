"""Download remote images into the session workspace for GenUi preview URLs."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.web.polite_http import polite_stream, public_fetch_user_agent
from leagent.tools.web.robots_policy import assert_fetch_allowed

logger = structlog.get_logger(__name__)

_SOFT_DEFAULT_BYTES = 25 * 1024 * 1024


def _download_size_limits() -> tuple[int, int]:
    """Return (hard_cap, default_requested) from FilesSettings."""
    from leagent.config.settings import get_settings

    hard = max(1, int(get_settings().files.max_upload_bytes))
    default = min(_SOFT_DEFAULT_BYTES, hard)
    return hard, default


class WebImageDownloadTool(BaseTool):
    """Fetch an image URL and register it as a session attachment (same shape as uploads)."""

    name = "web_image_download"
    description = (
        "Download an image from an HTTPS URL into the current chat session workspace. "
        "Returns file id and `/api/v1/files/{id}/preview` path for use in `emit_ui_tree` Image nodes."
    )
    category = ToolCategory.WEB
    version = "1.0.0"
    timeout_sec = 120
    is_read_only = False
    is_concurrency_safe = True

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["url"],
            "additionalProperties": False,
            "properties": {
                "url": {"type": "string", "description": "HTTPS URL of an image"},
                "filename": {"type": "string", "description": "Optional filename hint (extension inferred if omitted)"},
                "max_bytes": {
                    "type": "integer",
                    "description": "Maximum download size in bytes (default 25MB, capped by FILES_MAX_UPLOAD_BYTES)",
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        raw_url = str(params.get("url") or "").strip()
        if not raw_url.startswith("https://"):
            raise ValueError("url must be an https:// URL")

        if not context.session_id:
            raise ValueError("session_id is required on tool context")

        session_id = UUID(context.session_id)
        user_uuid = UUID(str(context.user_id)) if context.user_id else None

        hard_cap, default_dl = _download_size_limits()
        max_bytes = int(params.get("max_bytes") or default_dl)
        if max_bytes <= 0:
            max_bytes = default_dl
        max_bytes = min(max_bytes, hard_cap)

        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0, trust_env=True) as client:
            await assert_fetch_allowed(client, raw_url)
            headers = {"User-Agent": public_fetch_user_agent()}
            async with polite_stream(client, "GET", raw_url, headers=headers) as resp:
                resp.raise_for_status()
                ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                if not ctype.startswith("image/"):
                    raise ValueError(f"response is not an image (content-type={ctype!r})")

                total = 0
                chunks: list[bytes] = []
                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError(f"download exceeds max_bytes ({max_bytes})")
                    chunks.append(chunk)

        data = b"".join(chunks)
        if not data:
            raise ValueError("empty image response")

        ext = mimetypes.guess_extension(ctype) or ".bin"
        if ext == ".jpe":
            ext = ".jpg"

        hint = params.get("filename")
        safe_name = Path(hint.strip()).name if isinstance(hint, str) and hint.strip() else f"download{ext}"

        from leagent.file.tool_output import register_tool_artifact

        out = await register_tool_artifact(
            data,
            filename=safe_name,
            content_type=ctype,
            session_id=session_id,
            user_id=user_uuid,
        )

        if out is None:
            raise RuntimeError("failed to register downloaded image")

        fid = str(out.get("id") or "")
        preview_path = f"/api/v1/files/{fid}/preview"
        return {
            "file_id": fid,
            "preview_path": preview_path,
            "content_type": ctype,
            "bytes": len(data),
            "preview_url": out.get("preview_url"),
            "download_url": out.get("download_url"),
        }
