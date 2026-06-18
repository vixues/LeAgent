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
GENERATION_KINDS = ("image", "video", "model3d", "vfx", "audio")


@dataclass
class GenerationRequest:
    """Standardized, typed request envelope for one generation invocation.

    All backends share this shape so a request can be validated, logged, and
    routed uniformly regardless of whether it lands on a local pipeline, an
    external HTTP service, or the offline floor. ``params`` carries the
    kind-specific knobs (size / steps / duration / frames / conditioning).
    Backends still receive the flattened ``**params`` for backward
    compatibility; :meth:`as_params` produces that mapping.
    """

    kind: str
    prompt: str = ""
    provider: str | None = None
    model: str | None = None
    #: Optional conditioning inputs (by-reference MediaRef dicts).
    image: dict[str, Any] | None = None
    controlnet: dict[str, Any] | None = None
    camera: dict[str, Any] | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> str | None:
        """Return an error message when the request is malformed, else ``None``."""
        if self.kind not in GENERATION_KINDS:
            return f"unsupported kind '{self.kind}'"
        if not (self.prompt or "").strip() and self.image is None:
            return "a prompt or a conditioning image is required"
        return None

    def as_params(self) -> dict[str, Any]:
        """Flatten conditioning + extra params into the backend kwarg mapping."""
        out: dict[str, Any] = dict(self.params)
        if self.model:
            out.setdefault("model", self.model)
        if self.image is not None:
            out["image"] = self.image
        if self.controlnet is not None:
            out["controlnet"] = self.controlnet
        if self.camera is not None:
            out["camera"] = self.camera
        return out

    @classmethod
    def from_params(
        cls, *, kind: str, prompt: str, provider: str | None = None, **params: Any
    ) -> "GenerationRequest":
        """Build a request from the loose ``generate(**params)`` call shape."""
        return cls(
            kind=kind,
            prompt=prompt,
            provider=provider,
            model=params.pop("model", None),
            image=params.pop("image", None),
            controlnet=params.pop("controlnet", None),
            camera=params.pop("camera", None),
            params=params,
        )


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
    "GenerationRequest",
]
