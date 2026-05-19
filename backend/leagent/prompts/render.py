"""Provider-specific rendering of :class:`LayerResult` lists.

Three renderers exist:

* :class:`OpenAIRenderer` — concatenates non-empty layers with two
  newlines; returns a single ``{"role": "system", "content": str}``
  message. The stable prefix cache marker is a no-op because OpenAI
  currently has no per-message cache control.
* :class:`AnthropicRenderer` — splits the prompt on layers whose
  ``cache_boundary`` flag is set, emitting a single system message
  with multiple content blocks where the prefix carries
  ``cache_control: {"type": "ephemeral"}``.
* :class:`PlainRenderer` — returns just the concatenated text (used by
  the legacy ``AgentController`` path and the rule judge).
"""

from __future__ import annotations

from typing import Any

from leagent.prompts.types import LayerResult, RenderTarget


def _concat(layers: list[LayerResult]) -> str:
    parts = [layer.body.rstrip() for layer in layers if layer.body.strip()]
    return "\n\n".join(parts)


class PlainRenderer:
    target = RenderTarget.PLAIN

    def render(
        self, layers: list[LayerResult]
    ) -> tuple[str, list[dict[str, Any]]]:
        text = _concat(layers)
        return text, []


class OpenAIRenderer:
    target = RenderTarget.OPENAI

    def render(
        self, layers: list[LayerResult]
    ) -> tuple[str, list[dict[str, Any]]]:
        text = _concat(layers)
        if not text:
            return "", []
        return text, [{"role": "system", "content": text}]


class AnthropicRenderer:
    target = RenderTarget.ANTHROPIC

    def __init__(self, *, enable_cache_boundaries: bool = True) -> None:
        self._enable_cache = enable_cache_boundaries

    def render(
        self, layers: list[LayerResult]
    ) -> tuple[str, list[dict[str, Any]]]:
        text = _concat(layers)
        if not text:
            return "", []

        if not self._enable_cache:
            return text, [{"role": "system", "content": text}]

        blocks: list[dict[str, Any]] = []
        buffer: list[str] = []
        cacheable = True
        for layer in layers:
            body = layer.body.strip()
            if not body:
                continue
            buffer.append(body)
            if layer.cache_boundary and cacheable:
                chunk = "\n\n".join(buffer)
                blocks.append(
                    {
                        "type": "text",
                        "text": chunk,
                        "cache_control": {"type": "ephemeral"},
                    }
                )
                buffer.clear()
                cacheable = False
        if buffer:
            blocks.append({"type": "text", "text": "\n\n".join(buffer)})
        messages = [{"role": "system", "content": blocks}]
        return text, messages


def get_renderer(target: RenderTarget, *, enable_cache_boundaries: bool = True):
    if target is RenderTarget.OPENAI:
        return OpenAIRenderer()
    if target is RenderTarget.ANTHROPIC:
        return AnthropicRenderer(enable_cache_boundaries=enable_cache_boundaries)
    return PlainRenderer()


__all__ = [
    "AnthropicRenderer",
    "OpenAIRenderer",
    "PlainRenderer",
    "get_renderer",
]
