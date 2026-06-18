"""Generation backends — Strategy implementations for media production."""

from leagent.llm.generation.backends.configured import ConfiguredGenerationBackend
from leagent.llm.generation.backends.dashscope_image import DashScopeImageBackend
from leagent.llm.generation.backends.elevenlabs import ElevenLabsBackend
from leagent.llm.generation.backends.http import (
    HttpMesh3DBackend,
    HttpUpscaleBackend,
    HttpVfxBackend,
    HttpVideoBackend,
)
from leagent.llm.generation.backends.local_diffusion import LocalDiffusionBackend
from leagent.llm.generation.backends.offline import OfflineGenerationBackend
from leagent.llm.generation.backends.openai_image import ImageProviderBackend, OpenAIImageBackend
from leagent.llm.generation.backends.replicate import ReplicateBackend
from leagent.llm.generation.backends.siliconflow import SiliconFlowImageBackend

__all__ = [
    "ConfiguredGenerationBackend",
    "DashScopeImageBackend",
    "ElevenLabsBackend",
    "HttpMesh3DBackend",
    "HttpUpscaleBackend",
    "HttpVfxBackend",
    "HttpVideoBackend",
    "ImageProviderBackend",
    "LocalDiffusionBackend",
    "OfflineGenerationBackend",
    "OpenAIImageBackend",
    "ReplicateBackend",
    "SiliconFlowImageBackend",
]
