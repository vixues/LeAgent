"""Shared helpers for chat-callable media-generation tools.

The ``image_generate`` / ``video_generate`` / ``audio_generate`` tools all
route through the unified :class:`~leagent.llm.generation.GenerationService`
so chat respects the locally configured providers/presets (admin-managed in
``providers.yaml``). This module centralises preset resolution + generation +
artifact persistence so each tool stays a thin, declarative wrapper.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from leagent.utils.logging import get_logger

if TYPE_CHECKING:
    from leagent.tools.base import ToolContext

logger = get_logger(__name__)

#: Default download/display extension per media kind.
_KIND_EXT = {"image": "png", "video": "mp4", "audio": "mp3", "model3d": "glb", "vfx": "png"}

#: Generic backend placeholders that must not surface as display names.
_WEAK_FILENAMES = frozenset(
    {
        "image.png",
        "image.jpg",
        "image.jpeg",
        "image.webp",
        "image.gif",
        "video.mp4",
        "video.webm",
        "audio.mp3",
        "audio.wav",
        "file.bin",
        "file",
        "download.bin",
        "bin",
    }
)

_MAX_STEM_LEN = 48


def resolve_preset_params(
    kind: str,
    *,
    preset_id: str | None,
    provider: str | None,
) -> tuple[str | None, str | None, dict[str, Any]]:
    """Resolve ``(provider, model, params)`` from an explicit or default preset.

    Mirrors ``BaseGenerationNode._resolve_preset``: an explicit preset id wins;
    otherwise, when no provider override is given, the workflow-level default
    preset is applied so chat honours the admin "active model" switch.
    """
    try:
        from leagent.llm.generation import get_image_gen_config

        store = get_image_gen_config()
    except Exception:  # noqa: BLE001 - presets are optional
        return provider, None, {}

    preset = None
    pid = str(preset_id or "").strip()
    if pid and pid.lower() not in ("auto", "none"):
        preset = store.get_preset(pid)
    elif provider in (None, "", "auto"):
        # Only honour the workflow default when it targets this media kind.
        default = store.default_preset()
        if default is not None and (default.kind or "image") == kind:
            preset = default

    if preset is None:
        return (None if provider in ("auto", "", None) else provider), None, {}

    resolved_provider = provider
    if provider in (None, "", "auto") and preset.backend and preset.backend != "auto":
        resolved_provider = preset.backend
    return resolved_provider, (preset.model or None), dict(preset.params or {})


def _is_weak_filename(name: str | None) -> bool:
    if not name or not str(name).strip():
        return True
    return Path(str(name)).name.strip().lower() in _WEAK_FILENAMES


def _with_extension(stem: str, ext: str) -> str:
    clean_ext = ext.lstrip(".")
    return f"{stem}.{clean_ext}" if clean_ext else stem


def _stem_from_prompt(prompt: str, *, max_len: int = _MAX_STEM_LEN) -> str:
    """Derive a short filesystem-safe stem from a generation prompt."""
    from leagent.file.primitives import sanitize_filename

    text = " ".join((prompt or "").split())
    if not text:
        return ""
    # Keep the leading phrase so names stay readable for long prompts.
    if len(text) > max_len * 2:
        cut = text[: max_len * 2]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        text = cut
    stem = sanitize_filename(text, default="", max_length=max_len)
    return stem.strip("._-")


def _unique_stem(stem: str, taken: set[str] | None, ext: str) -> str:
    """Return a stem whose ``stem.ext`` is not already in *taken* (case-insensitive)."""
    taken_cf = {n.casefold() for n in (taken or ()) if n}
    if _with_extension(stem, ext).casefold() not in taken_cf:
        return stem
    for i in range(2, 1000):
        alt = f"{stem}_{i}"
        if _with_extension(alt, ext).casefold() not in taken_cf:
            return alt
    return f"{stem}_{uuid4().hex[:6]}"


def build_media_filename(
    *,
    kind: str,
    prompt: str,
    ext: str,
    preferred: str | None = None,
    backend_filename: str | None = None,
    taken: set[str] | None = None,
) -> str:
    """Build a distinguishable display filename for a generated media artifact.

    Priority:
    1. Explicit *preferred* name (tool ``filename`` / ``output_path`` basename)
       when it is not a weak placeholder.
    2. Short slug derived from *prompt*.
    3. ``{kind}_{hex8}`` fallback.

    Auto-derived names always get a short unique suffix; explicit names are
    de-duplicated against *taken* with ``_2``, ``_3``, … suffixes.
    """
    from leagent.file.primitives import sanitize_filename

    clean_ext = (ext or "bin").lstrip(".") or "bin"
    explicit = False
    stem: str | None = None

    if preferred and not _is_weak_filename(preferred):
        raw = sanitize_filename(Path(preferred).name, default="")
        if raw:
            path = Path(raw)
            # Drop a matching (or any) extension so we can re-attach *clean_ext*.
            stem = (path.stem if path.suffix else path.name).strip("._-") or None
            explicit = stem is not None

    if not stem and backend_filename and not _is_weak_filename(backend_filename):
        raw = sanitize_filename(Path(backend_filename).name, default="")
        if raw:
            path = Path(raw)
            stem = (path.stem if path.suffix else path.name).strip("._-") or None

    if not stem:
        stem = _stem_from_prompt(prompt) or None

    if not stem:
        return _with_extension(f"{kind}_{uuid4().hex[:8]}", clean_ext)

    if explicit:
        stem = _unique_stem(stem, taken, clean_ext)
    else:
        # Prompt/auto names: always uniquify so Files tab never shows clones.
        unique = uuid4().hex[:6]
        max_base = max(8, _MAX_STEM_LEN - len(unique) - 1)
        if len(stem) > max_base:
            stem = stem[:max_base].rstrip("._-") or kind
        stem = _unique_stem(f"{stem}_{unique}", taken, clean_ext)

    return _with_extension(stem, clean_ext)


async def _session_taken_filenames(context: ToolContext) -> set[str]:
    """Best-effort set of existing attachment filenames in the current session."""
    taken: set[str] = set()
    session_id = getattr(context, "session_id", None)
    if not session_id:
        return taken
    try:
        from uuid import UUID

        from leagent.services.service_manager import get_service_manager

        sm = get_service_manager()
        session_manager = getattr(sm, "session_manager", None) if sm else None
        if session_manager is None:
            return taken
        sid = session_id if isinstance(session_id, UUID) else UUID(str(session_id))
        for att in await session_manager.list_attachments(sid):
            name = getattr(att, "filename", None) or getattr(att, "name", None)
            if name:
                taken.add(str(name))
    except Exception:  # noqa: BLE001 - naming must never fail generation
        logger.debug("media_taken_filenames_lookup_failed", exc_info=True)
    return taken


async def generate_media(
    context: ToolContext,
    *,
    kind: str,
    prompt: str,
    preset_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    output_path: str | None = None,
    filename: str | None = None,
    max_retries: int = 2,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate one asset of *kind* and persist it as a managed artifact.

    Returns a chat-friendly result dict including ``preview_path`` so
    ``emit_ui_tree`` media nodes can render the produced asset.
    """
    from leagent.llm.generation import get_generation_service

    provider_arg, preset_model, params = resolve_preset_params(
        kind, preset_id=preset_id, provider=provider
    )
    if extra_params:
        for key, value in extra_params.items():
            if value is not None:
                params[key] = value
    if isinstance(model, str) and model.strip():
        params["model"] = model.strip()
    elif preset_model:
        params.setdefault("model", preset_model)

    start = time.perf_counter()
    out = await get_generation_service().generate(
        kind=kind,
        prompt=prompt,
        provider=provider_arg,
        max_retries=max_retries,
        **params,
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    result: dict[str, Any] = {
        "success": bool(out.success),
        "kind": kind,
        "provider": out.provider,
        "model": out.model,
        "mime": out.mime,
        "elapsed_ms": elapsed_ms,
        "placeholder": bool(out.meta.get("placeholder")),
    }
    if not out.success:
        result["error"] = out.error or "generation failed"
        return result
    if out.meta.get("url"):
        result["url"] = out.meta["url"]

    if out.data:
        ext = _KIND_EXT.get(kind, "bin")
        preferred = None
        if isinstance(filename, str) and filename.strip():
            preferred = filename.strip()
        elif isinstance(output_path, str) and output_path.strip():
            preferred = Path(output_path).name
        taken = await _session_taken_filenames(context)
        display_name = build_media_filename(
            kind=kind,
            prompt=prompt,
            ext=ext,
            preferred=preferred,
            backend_filename=out.filename,
            taken=taken,
        )
        try:
            from leagent.file.tool_output import register_tool_artifact

            reg = await register_tool_artifact(
                out.data,
                filename=display_name,
                content_type=out.mime or None,
                session_id=context.session_id,
                user_id=context.user_id,
            )
        except Exception:  # noqa: BLE001
            logger.warning("media_generate_register_failed", kind=kind, exc_info=True)
            reg = None
        if reg:
            fid = str(reg.get("id") or "")
            result["file_id"] = fid
            result["filename"] = display_name
            result["file_size_bytes"] = reg.get("size")
            if kind == "image":
                result["kind"] = "image"
            if fid:
                result["preview_path"] = f"/api/v1/files/{fid}/preview"
            result["preview_url"] = reg.get("preview_url")
            result["download_url"] = reg.get("download_url")
            result["output_path"] = reg.get("storage_path")
            result["storage_path"] = reg.get("storage_path")

    logger.info("media_generated", kind=kind, provider=out.provider, model=out.model, elapsed_ms=elapsed_ms)
    return result


__all__ = ["build_media_filename", "generate_media", "resolve_preset_params"]
