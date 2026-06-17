"""Helpers for building multimodal chat messages from attachments."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from leagent.llm.base import ChatMessage, MessageRole
from leagent.llm.model_registry import ModelRegistry

_IMAGE_MIME_PREFIX = "image/"
_MAX_INLINE_IMAGE_BYTES = 8 * 1024 * 1024

TEXT_ONLY_IMAGE_ATTACHMENT_HINT = (
    "\n\nNote: The selected chat model does not accept inline images. "
    "Use the attached file paths (also listed in session_attachments) with tools "
    "such as `image_ocr`, `code_execution` (Pillow/OpenCV/imageio), or other file "
    "tools to read, transform, or analyze image files. "
    "Prefer code-based processing when the task is editing or converting images "
    "rather than describing their visual content."
)


def prepare_user_message_with_attachments(
    text: str,
    attachment_paths: list[str] | None,
    *,
    provider: str | None,
    model: str | None,
    catalog: ModelRegistry | None,
) -> str | dict[str, Any]:
    """Build the user turn payload for the agent loop.

    Text-only models receive file paths plus a tool hint; vision-capable models
    receive inline image blocks when attachments are small enough.
    """
    image_paths = [
        p for p in (attachment_paths or [])
        if isinstance(p, str) and p and is_image_path(p) and Path(p).is_file()
    ]
    if not image_paths:
        return text

    inline_images = model_supports_image_input(
        provider=provider,
        model=model,
        catalog=catalog,
    )
    if not inline_images:
        return f"{text}{TEXT_ONLY_IMAGE_ATTACHMENT_HINT}"

    try:
        mm = build_multimodal_user_message(text, attachment_paths)
        if isinstance(mm.content, list):
            return mm.to_openai_format()
    except Exception:
        pass
    return f"{text}{TEXT_ONLY_IMAGE_ATTACHMENT_HINT}"


def is_image_path(path: str) -> bool:
    """Return True when the path looks like a supported raster image."""
    mime, _ = mimetypes.guess_type(path)
    return bool(mime and mime.startswith(_IMAGE_MIME_PREFIX))


def image_path_to_data_url(path: str) -> str:
    """Encode an image path as a data URL for OpenAI-style multimodal messages."""
    p = Path(path)
    raw = p.read_bytes()
    if len(raw) > _MAX_INLINE_IMAGE_BYTES:
        raise ValueError(f"Image attachment too large for inline multimodal input: {path}")
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def model_supports_image_input(
    *,
    provider: str | None,
    model: str | None,
    catalog: ModelRegistry | None,
) -> bool:
    """Return True when the selected model can receive inline image blocks."""
    return model_supports_input_modality(
        "image", provider=provider, model=model, catalog=catalog
    )


def model_supports_input_modality(
    modality: str,
    *,
    provider: str | None,
    model: str | None,
    catalog: ModelRegistry | None,
) -> bool:
    """Whether the selected model accepts *modality* input, via the capability layer.

    Unknown models default to permissive (``True``) so callers fall back to the
    existing inline-or-tools handling rather than silently dropping content.
    """
    if catalog is None or not provider or not model:
        return True
    spec = catalog.get_spec(provider, model)
    if spec is None:
        return True
    from leagent.llm.capabilities import Modality, from_model_spec

    try:
        return from_model_spec(spec).supports_input(Modality(modality))
    except ValueError:
        return False


def model_supports_output_modality(
    modality: str,
    *,
    provider: str | None,
    model: str | None,
    catalog: ModelRegistry | None,
) -> bool:
    """Whether the selected model can natively produce *modality* output.

    Unlike input checks this defaults to ``False`` for unknown models: native
    media output is an opt-in capability, not a permissive fallback.
    """
    if catalog is None or not provider or not model:
        return False
    spec = catalog.get_spec(provider, model)
    if spec is None:
        return False
    from leagent.llm.capabilities import Modality, from_model_spec

    try:
        return from_model_spec(spec).supports_output(Modality(modality))
    except ValueError:
        return False


def model_supported_input_modalities(
    *,
    provider: str | None,
    model: str | None,
    catalog: ModelRegistry | None,
) -> set[str]:
    """Return the set of input modalities the selected model accepts."""
    if catalog is None or not provider or not model:
        return {"text", "image"}
    spec = catalog.get_spec(provider, model)
    if spec is None:
        return {"text", "image"}
    from leagent.llm.capabilities import from_model_spec

    return {m.value for m in from_model_spec(spec).inputs}


def has_image_attachments(attachment_paths: list[str] | None) -> bool:
    return any(
        isinstance(p, str) and p and is_image_path(p) and Path(p).is_file()
        for p in (attachment_paths or [])
    )


def build_multimodal_user_message(
    text: str,
    attachment_paths: list[str] | None,
) -> ChatMessage:
    """Build a user message with image attachments as multimodal content blocks.

    Non-image attachments stay out of the message body; they are still surfaced
    through the session attachment manifest and file tools.
    """
    image_paths = [
        p for p in (attachment_paths or [])
        if isinstance(p, str) and p and is_image_path(p) and Path(p).is_file()
    ]
    if not image_paths:
        return ChatMessage(role=MessageRole.USER, content=text)

    content: list[dict[str, Any]] = []
    if text.strip():
        content.append({"type": "text", "text": text})
    for path in image_paths:
        content.append({"type": "image_url", "image_url": {"url": image_path_to_data_url(path)}})
    return ChatMessage(role=MessageRole.USER, content=content)  # type: ignore[arg-type]
