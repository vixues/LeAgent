"""Core types for the unified generation service.

The generation layer is a first-class **Strategy + Registry**: each
:class:`GenerationBackend` is a strategy that knows how to produce one or
more media *kinds* (``image`` / ``video`` / ``model3d``); the
:class:`~leagent.llm.generation.service.GenerationService` selects and
orders strategies, applies retries, and fails over between providers.

This is deliberately *not* lifted into workflow nodes by a factory —
hand-authored art nodes call the service directly, keeping node authoring
explicit and composable (ComfyUI-style).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

#: Media kinds the generation layer understands.
GENERATION_KINDS = ("image", "video", "model3d")


@dataclass
class GenerationOutput:
    """Uniform envelope for one generation invocation."""

    success: bool
    kind: str
    data: bytes | None = None
    mime: str = ""
    filename: str = ""
    provider: str = ""
    model: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @classmethod
    def failure(cls, kind: str, error: str, **kw: Any) -> "GenerationOutput":
        return cls(success=False, kind=kind, error=error, **kw)


class GenerationError(RuntimeError):
    """Raised when a backend invocation fails in a retryable way."""


@runtime_checkable
class GenerationBackend(Protocol):
    """Strategy protocol every generation backend implements."""

    #: Provider id, e.g. ``openai`` / ``dashscope`` / ``offline``.
    name: str
    #: Media kinds this backend can produce.
    kinds: tuple[str, ...]

    def available(self) -> bool:
        """Whether this backend is usable (credentials present, etc.)."""
        ...

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        """Produce one asset of ``kind`` from ``prompt``."""
        ...


__all__ = [
    "GENERATION_KINDS",
    "GenerationBackend",
    "GenerationError",
    "GenerationOutput",
]
