"""Unified generation service (image / video / 3D).

A first-class **Strategy + Registry** that hand-authored art workflow
nodes call directly — no adapter→node factory. Backends declare which
media *kinds* they produce; the :class:`GenerationService` selects,
retries, and fails over between them, with a deterministic offline floor.
"""

from __future__ import annotations

from .backends import (
    HttpMesh3DBackend,
    HttpVideoBackend,
    ImageProviderBackend,
    LocalDiffusionBackend,
    OfflineGenerationBackend,
)
from .base import (
    GENERATION_KINDS,
    GenerationBackend,
    GenerationError,
    GenerationOutput,
)
from .service import (
    GenerationService,
    build_default_generation_service,
    get_generation_service,
    reset_generation_service,
)

__all__ = [
    "GENERATION_KINDS",
    "GenerationBackend",
    "GenerationError",
    "GenerationOutput",
    "GenerationService",
    "HttpMesh3DBackend",
    "HttpVideoBackend",
    "ImageProviderBackend",
    "LocalDiffusionBackend",
    "OfflineGenerationBackend",
    "build_default_generation_service",
    "get_generation_service",
    "reset_generation_service",
]
