"""Harvest tool/workspace artifacts for IM outbound delivery.

Chat tools (especially ``image_generate`` / ``web_image_download``) often
expose managed ``file_id`` / ``preview_path`` URLs. Channel adapters must
resolve those to bytes and send native media — not paste preview links into
WeChat.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import UUID

_FILE_API_RE = re.compile(
    r"/api/v1/files/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/(?:preview|download|content)\b"
)
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_BARE_PREVIEW_RE = re.compile(
    r"https?://[^\s)\"']+/api/v1/files/"
    r"[0-9a-fA-F-]{36}/(?:preview|download|content)\b"
    r"|/api/v1/files/[0-9a-fA-F-]{36}/(?:preview|download|content)\b",
    re.IGNORECASE,
)
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _as_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _normalize_path(path: str | None) -> str | None:
    if not path:
        return None
    raw = path.strip()
    if not raw or raw.startswith("/api/"):
        return None
    try:
        return str(Path(raw).expanduser().resolve())
    except OSError:
        return raw


def file_id_from_url(url: str) -> str | None:
    match = _FILE_API_RE.search(url or "")
    return match.group(1) if match else None


def _filename_from_mapping(item: dict[str, Any], path: str | None) -> str | None:
    name = (
        _as_str(item.get("filename"))
        or _as_str(item.get("name"))
        or _as_str(item.get("display_name"))
    )
    if name and name.lower() not in {"file.bin", "file", "download.bin", "bin"}:
        return name
    if path:
        leaf = Path(path).name
        if leaf and leaf.lower() not in {"file.bin", "bin"}:
            return leaf
    return name  # may still be weak; caller can replace from FileRef


def artifact_from_mapping(
    item: dict[str, Any],
    *,
    allow_generic_id: bool = False,
) -> dict[str, Any] | None:
    """Normalise one tool/attachment mapping into an outbound artifact dict."""
    file_id = _as_str(item.get("file_id")) or _as_str(item.get("attachment_id"))
    if not file_id and allow_generic_id:
        candidate = _as_str(item.get("id"))
        if candidate and _UUID_RE.match(candidate):
            # Only trust generic ``id`` when the row looks like a managed file.
            if any(
                item.get(k)
                for k in (
                    "storage_path",
                    "preview_path",
                    "preview_url",
                    "download_url",
                    "content_type",
                    "mime",
                    "filename",
                    "name",
                )
            ):
                file_id = candidate

    path = _normalize_path(
        _as_str(item.get("storage_path"))
        or _as_str(item.get("source_tool_path"))
        or _as_str(item.get("output_path"))
        or _as_str(item.get("path"))
        or _as_str(item.get("file_path"))
        or _as_str(item.get("saved_path"))
    )
    preview = _as_str(item.get("preview_path")) or _as_str(item.get("preview_url"))
    download = _as_str(item.get("download_url"))
    if not file_id and preview:
        file_id = file_id_from_url(preview)
    if not file_id and download:
        file_id = file_id_from_url(download)
    if not file_id and not path:
        return None

    content_type = (
        _as_str(item.get("content_type"))
        or _as_str(item.get("mime"))
        or _as_str(item.get("contentType"))
    )
    kind = _as_str(item.get("kind"))
    if not kind and content_type and content_type.lower().startswith("image/"):
        kind = "image"

    filename = _filename_from_mapping(item, path) or (
        "image.png" if kind == "image" else "file.bin"
    )

    out: dict[str, Any] = {"filename": filename}
    if file_id:
        out["file_id"] = file_id
    if path:
        out["path"] = path
    if content_type:
        out["content_type"] = content_type
    if kind:
        out["kind"] = kind
    return out


def _is_tool_result_frame(data: dict[str, Any]) -> bool:
    return "tool_use_id" in data or (
        "envelope" in data and "name" in data and "success" in data
    )


def harvest_artifacts_from_payload(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Collect outbound artifacts from a workspace_attachments or tool_result payload."""
    if not isinstance(data, dict):
        return []
    found: list[dict[str, Any]] = []

    def add(raw: Any, *, allow_generic_id: bool = False) -> None:
        if isinstance(raw, dict):
            art = artifact_from_mapping(raw, allow_generic_id=allow_generic_id)
            if art:
                found.append(art)
        elif isinstance(raw, str) and raw.strip():
            text = raw.strip()
            fid = file_id_from_url(text)
            if fid:
                found.append(
                    {
                        "file_id": fid,
                        "filename": "image.png",
                        "kind": "image",
                    }
                )
                return
            art = artifact_from_mapping({"path": text})
            if art:
                found.append(art)

    # Wire ``tool_result`` frames: dig into envelope only (avoid tool_use_id etc.).
    if _is_tool_result_frame(data):
        envelope = data.get("envelope")
        if isinstance(envelope, dict):
            env_data = envelope.get("data")
            if isinstance(env_data, dict):
                found.extend(harvest_artifacts_from_payload(env_data))
            elif env_data is not None:
                add(env_data)
        # Truncated content may still embed preview paths.
        content = data.get("content")
        if isinstance(content, str):
            for fid in harvest_file_ids_from_text(content):
                found.append({"file_id": fid, "filename": "image.png", "kind": "image"})
        return found

    for key in ("attachments", "managed_artifacts"):
        value = data.get(key)
        if isinstance(value, list):
            for item in value:
                add(item, allow_generic_id=True)

    for key in ("produced_files", "images", "files"):
        value = data.get(key)
        if isinstance(value, list):
            for item in value:
                add(item, allow_generic_id=True)

    for path in data.get("paths") or []:
        add(path)

    # Top-level image_generate / web_image_download / document_generate shape.
    if any(
        data.get(k)
        for k in (
            "file_id",
            "preview_path",
            "preview_url",
            "storage_path",
            "output_path",
            "download_url",
        )
    ):
        add(data, allow_generic_id=False)

    return found


def harvest_file_ids_from_text(text: str) -> list[str]:
    """Extract managed file ids referenced in assistant markdown/plain text."""
    if not text:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for match in _FILE_API_RE.finditer(text):
        fid = match.group(1)
        if fid not in seen:
            seen.add(fid)
            ordered.append(fid)
    return ordered


def _merge_artifact(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key in ("file_id", "path", "content_type", "kind"):
        if not merged.get(key) and extra.get(key):
            merged[key] = extra[key]
    # Prefer a real filename over placeholders.
    weak = {"file.bin", "file", "image.png", "download.bin", "bin"}
    base_name = str(merged.get("filename") or "").lower()
    extra_name = str(extra.get("filename") or "")
    if extra_name and (base_name in weak or not merged.get("filename")):
        if extra_name.lower() not in weak or not merged.get("filename"):
            merged["filename"] = extra_name
    if extra.get("kind") == "image" or str(extra.get("content_type") or "").startswith(
        "image/"
    ):
        merged["kind"] = "image"
    return merged


def dedupe_artifacts(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe by file_id **and** path (same file often appears as both)."""
    out: list[dict[str, Any]] = []
    by_id: dict[str, int] = {}
    by_path: dict[str, int] = {}

    for art in artifacts:
        if not isinstance(art, dict):
            continue
        fid = _as_str(art.get("file_id"))
        path = _normalize_path(_as_str(art.get("path")))
        if path:
            art = {**art, "path": path}
        if not fid and not path:
            continue

        idx: int | None = None
        if fid and fid in by_id:
            idx = by_id[fid]
        elif path and path in by_path:
            idx = by_path[path]

        if idx is not None:
            out[idx] = _merge_artifact(out[idx], art)
            merged = out[idx]
            mf = _as_str(merged.get("file_id"))
            mp = _normalize_path(_as_str(merged.get("path")))
            if mf:
                by_id[mf] = idx
            if mp:
                by_path[mp] = idx
            continue

        idx = len(out)
        out.append(art)
        if fid:
            by_id[fid] = idx
        if path:
            by_path[path] = idx
    return out


def strip_delivered_file_links(
    text: str,
    *,
    file_ids: list[str] | None = None,
    strip_all_file_api_links: bool = True,
) -> str:
    """Remove preview/download markdown and bare File API URLs from IM text."""
    if not text:
        return ""
    ids = {fid.lower() for fid in (file_ids or []) if fid}

    def keep_md(match: re.Match[str]) -> str:
        url = match.group(1) or ""
        fid = file_id_from_url(url)
        if strip_all_file_api_links and fid:
            return ""
        if ids and fid and fid.lower() in ids:
            return ""
        return match.group(0)

    cleaned = _MD_IMAGE_RE.sub(keep_md, text)
    if strip_all_file_api_links or ids:
        cleaned = _BARE_PREVIEW_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


async def load_artifact_bytes(artifact: dict[str, Any]) -> tuple[bytes, str, str]:
    """Resolve artifact bytes → ``(data, filename, content_type)``.

    Prefers ``file_id`` via FileService when present (canonical managed blob);
    falls back to a readable local ``path``.
    """
    import mimetypes

    filename = _as_str(artifact.get("filename")) or "file.bin"
    content_type = _as_str(artifact.get("content_type")) or ""
    file_id = _as_str(artifact.get("file_id"))
    path = _normalize_path(_as_str(artifact.get("path")))

    # Prefer managed identity — avoids stale path duplicates / wrong names.
    if file_id:
        from leagent.services.service_manager import get_service_manager

        sm = get_service_manager()
        file_service = getattr(sm, "file_service", None)
        if file_service is None:
            runtime = getattr(sm, "runtime_context", None)
            file_service = getattr(runtime, "file_service", None) if runtime else None
        if file_service is None:
            raise RuntimeError("FileService unavailable for channel outbound media")

        ref = await file_service.resolve(UUID(file_id))
        if ref is None:
            raise FileNotFoundError(f"managed file not found: {file_id}")
        data, _ct = await file_service.download(ref)
        weak = {"file.bin", "file", "image.png", "download.bin", "bin"}
        name = (
            ref.filename
            if filename.lower() in weak and ref.filename
            else filename
        ) or (ref.filename or "file.bin")
        mime = content_type or ref.content_type or mimetypes.guess_type(name)[0] or ""
        return data, name, mime

    if path:
        src = Path(path)
        if src.is_file():
            data = src.read_bytes()
            if not content_type:
                content_type = mimetypes.guess_type(filename or src.name)[0] or ""
            name = filename if filename.lower() not in {"file.bin", "bin"} else src.name
            return data, name, content_type

    raise FileNotFoundError(f"artifact has neither readable path nor file_id: {artifact!r}")


def is_image_artifact(*, filename: str, content_type: str = "", kind: str = "") -> bool:
    import mimetypes

    mime = (content_type or "").lower()
    if mime.startswith("image/"):
        return True
    if (kind or "").lower() in {"image", "img", "picture"}:
        return True
    guessed = (mimetypes.guess_type(filename)[0] or "").lower()
    return guessed.startswith("image/")
