"""Shared helpers for chat-callable media-generation tools.

The ``image_generate`` / ``video_generate`` / ``audio_generate`` tools all
route through the unified :class:`~leagent.llm.generation.GenerationService`
so chat respects the locally configured providers/presets (admin-managed in
``providers.yaml``). This module centralises preset resolution + generation +
artifact persistence so each tool stays a thin, declarative wrapper.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from leagent.utils.logging import get_logger

if TYPE_CHECKING:
    from leagent.tools.base import ToolContext

logger = get_logger(__name__)

#: Default download/display extension per media kind.
_KIND_EXT = {"image": "png", "video": "mp4", "audio": "mp3", "model3d": "glb", "vfx": "png"}


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


async def generate_media(
    context: ToolContext,
    *,
    kind: str,
    prompt: str,
    preset_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    output_path: str | None = None,
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
        from pathlib import Path

        display_name = (
            Path(output_path).name
            if isinstance(output_path, str) and output_path.strip()
            else (out.filename or f"{kind}_{uuid4().hex[:8]}.{ext}")
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


__all__ = ["generate_media", "resolve_preset_params"]
