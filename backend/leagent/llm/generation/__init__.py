"""Unified generation service (image / video / 3D).

A first-class **Strategy + Registry** that hand-authored art workflow
nodes call directly — no adapter→node factory. Backends declare which
media *kinds* they produce; the :class:`GenerationService` selects,
retries, and fails over between them, with a deterministic offline floor.
"""

from __future__ import annotations

from .backends import (
    ConfiguredGenerationBackend,
    ElevenLabsBackend,
    HttpMesh3DBackend,
    HttpUpscaleBackend,
    HttpVfxBackend,
    HttpVideoBackend,
    ImageProviderBackend,
    LocalDiffusionBackend,
    OfflineGenerationBackend,
    ReplicateBackend,
    SiliconFlowImageBackend,
)
from .base import (
    GENERATION_KINDS,
    GenerationBackend,
    GenerationError,
    GenerationOutput,
    GenerationRequest,
)
from .config import (
    BACKEND_MODEL_CATALOG,
    CUSTOM_KINDS,
    CUSTOM_PROTOCOLS,
    CustomProvider,
    ImageGenConfigError,
    ImageGenConfigStore,
    ImageGenPreset,
    get_image_gen_config,
    local_models,
    reset_image_gen_config,
)
from .service import (
    GenerationService,
    build_default_generation_service,
    get_generation_service,
    reset_generation_service,
)

__all__ = [
    "BACKEND_MODEL_CATALOG",
    "CUSTOM_KINDS",
    "CUSTOM_PROTOCOLS",
    "GENERATION_KINDS",
    "ConfiguredGenerationBackend",
    "CustomProvider",
    "ElevenLabsBackend",
    "GenerationBackend",
    "GenerationError",
    "GenerationOutput",
    "GenerationRequest",
    "GenerationService",
    "ImageGenConfigError",
    "ImageGenConfigStore",
    "ImageGenPreset",
    "get_image_gen_config",
    "local_models",
    "reset_image_gen_config",
    "HttpMesh3DBackend",
    "HttpUpscaleBackend",
    "HttpVfxBackend",
    "HttpVideoBackend",
    "ImageProviderBackend",
    "LocalDiffusionBackend",
    "OfflineGenerationBackend",
    "ReplicateBackend",
    "SiliconFlowImageBackend",
    "build_default_generation_service",
    "get_generation_service",
    "reset_generation_service",
]
