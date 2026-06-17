"""Structured multimodal message content (ChatGPT-style content parts).

A chat message is no longer just a string: it can be an ordered list of typed
parts (text / image / file). This module provides:

* :class:`ContentPart` / :class:`MessageContent` — a serialisable representation
  that round-trips through DB JSON and converts to/from the OpenAI multimodal
  ``content`` array shape.
* :func:`rebuild_vision_history` — a capability-aware transform over OpenAI
  seed messages that reconstructs inline image blocks for recent user turns
  (multi-turn vision) and strips image blocks for text-only models.

It is deliberately provider-agnostic and dependency-light so it can be reused
by the agent controller, the query engine, and tests.
"""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Marker key carried on an OpenAI-format message holding the local image
#: paths that produced (or should produce) its inline vision blocks.
ATTACHMENT_IMAGE_PATHS_KEY = "_attachment_image_paths"

_IMAGE_MIME_PREFIX = "image/"
_MAX_INLINE_IMAGE_BYTES = 8 * 1024 * 1024


@dataclass
class ContentPart:
    """One typed unit of a multimodal message."""

    type: str  # "text" | "image" | "file"
    text: str | None = None
    url: str | None = None  # data: URL or remote URL (for images)
    mime: str | None = None
    file_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type}
        for key in ("text", "url", "mime", "file_id", "name"):
            value = getattr(self, key)
            if value is not None:
                d[key] = value
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ContentPart:
        return cls(
            type=str(raw.get("type") or "text"),
            text=raw.get("text"),
            url=raw.get("url"),
            mime=raw.get("mime"),
            file_id=raw.get("file_id"),
            name=raw.get("name"),
        )

    @classmethod
    def text_part(cls, text: str) -> ContentPart:
        return cls(type="text", text=text)

    @classmethod
    def image_part(cls, url: str, *, mime: str | None = None, file_id: str | None = None) -> ContentPart:
        return cls(type="image", url=url, mime=mime, file_id=file_id)

    def to_openai_block(self) -> dict[str, Any] | None:
        """Lower to an OpenAI ``content`` array block (None when not renderable)."""
        if self.type == "text":
            return {"type": "text", "text": self.text or ""}
        if self.type == "image" and self.url:
            return {"type": "image_url", "image_url": {"url": self.url}}
        return None


@dataclass
class MessageContent:
    """Ordered list of content parts for one message."""

    parts: list[ContentPart] = field(default_factory=list)

    @property
    def has_media(self) -> bool:
        return any(p.type != "text" for p in self.parts)

    @property
    def is_empty(self) -> bool:
        return not self.parts

    def text(self) -> str:
        return "\n".join(p.text or "" for p in self.parts if p.type == "text").strip()

    def to_dict_list(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self.parts]

    @classmethod
    def from_dict_list(cls, raw: Any) -> MessageContent:
        if not isinstance(raw, list):
            return cls()
        return cls(parts=[ContentPart.from_dict(p) for p in raw if isinstance(p, dict)])

    def to_openai_content(self) -> str | list[dict[str, Any]]:
        """Return a plain string (text-only) or an OpenAI multimodal array."""
        if not self.has_media:
            return self.text()
        blocks: list[dict[str, Any]] = []
        for part in self.parts:
            block = part.to_openai_block()
            if block is not None:
                blocks.append(block)
        return blocks or self.text()

    @classmethod
    def from_openai_content(cls, content: Any) -> MessageContent:
        if isinstance(content, str):
            return cls(parts=[ContentPart.text_part(content)] if content else [])
        if not isinstance(content, list):
            return cls()
        parts: list[ContentPart] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = str(block.get("type") or "").lower()
            if btype == "text":
                parts.append(ContentPart.text_part(str(block.get("text") or "")))
            elif btype in ("image_url", "image"):
                url = ""
                iu = block.get("image_url")
                if isinstance(iu, dict):
                    url = str(iu.get("url") or "")
                elif isinstance(iu, str):
                    url = iu
                if url:
                    parts.append(ContentPart.image_part(url))
        return cls(parts=parts)


# ---------------------------------------------------------------------------
# Multi-turn vision history
# ---------------------------------------------------------------------------


def is_image_path(path: str) -> bool:
    mime, _ = mimetypes.guess_type(path)
    return bool(mime and mime.startswith(_IMAGE_MIME_PREFIX))


def image_path_to_data_url(path: str) -> str | None:
    """Encode an image path as a data URL, or None when too large / unreadable."""
    try:
        p = Path(path)
        raw = p.read_bytes()
    except OSError:
        return None
    if len(raw) > _MAX_INLINE_IMAGE_BYTES:
        return None
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def content_has_image_block(content: Any) -> bool:
    if not isinstance(content, list):
        return False
    for block in content:
        if isinstance(block, dict):
            btype = str(block.get("type") or "").lower()
            if btype in ("image_url", "image", "input_image"):
                return True
    return False


def strip_image_blocks(content: Any) -> Any:
    """Collapse a multimodal content array down to its text (drop image blocks)."""
    if not isinstance(content, list):
        return content
    texts = [
        str(b.get("text") or "")
        for b in content
        if isinstance(b, dict) and str(b.get("type") or "").lower() == "text"
    ]
    joined = "\n".join(t for t in texts if t).strip()
    return joined


def rebuild_vision_history(
    messages: list[dict[str, Any]],
    *,
    supports_image: bool,
    max_images: int = 4,
) -> list[dict[str, Any]]:
    """Capability-aware rewrite of OpenAI seed messages for multi-turn vision.

    * When ``supports_image`` is False, every inline image block is stripped so
      a text-only model never receives (and errors on) vision content.
    * When ``supports_image`` is True, user messages carrying the
      :data:`ATTACHMENT_IMAGE_PATHS_KEY` metadata have their image blocks
      (re)built from those local paths, for up to ``max_images`` most-recent
      images across the conversation (older images are dropped to bound tokens).

    The marker key is always removed from the returned messages so nothing
    provider-incompatible leaks downstream.
    """
    out: list[dict[str, Any]] = []
    # Budget images from the most recent turn backwards.
    remaining = max(0, max_images)
    rebuilt: list[dict[str, Any]] = []
    for msg in reversed(messages):
        m = dict(msg)
        paths = m.pop(ATTACHMENT_IMAGE_PATHS_KEY, None)
        if not supports_image:
            if content_has_image_block(m.get("content")):
                m["content"] = strip_image_blocks(m.get("content"))
            rebuilt.append(m)
            continue
        if m.get("role") == "user" and isinstance(paths, list) and paths:
            text = m["content"] if isinstance(m.get("content"), str) else _content_text(m.get("content"))
            blocks: list[dict[str, Any]] = []
            if text:
                blocks.append({"type": "text", "text": text})
            for path in paths:
                if remaining <= 0:
                    break
                if not (isinstance(path, str) and path and is_image_path(path)):
                    continue
                url = image_path_to_data_url(path)
                if url is None:
                    continue
                blocks.append({"type": "image_url", "image_url": {"url": url}})
                remaining -= 1
            if any(b["type"] == "image_url" for b in blocks):
                m["content"] = blocks
        rebuilt.append(m)
    out = list(reversed(rebuilt))
    return out


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(b.get("text") or "")
            for b in content
            if isinstance(b, dict) and str(b.get("type") or "").lower() == "text"
        ).strip()
    return ""


__all__ = [
    "ATTACHMENT_IMAGE_PATHS_KEY",
    "ContentPart",
    "MessageContent",
    "content_has_image_block",
    "image_path_to_data_url",
    "is_image_path",
    "rebuild_vision_history",
    "strip_image_blocks",
]
