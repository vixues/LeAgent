"""Vendor HTTP clients for media generation (image providers)."""

from leagent.llm.generation.providers.base import ImageGenResult, ProviderResult
from leagent.llm.generation.providers.dashscope import DashScopeWanxProvider
from leagent.llm.generation.providers.openai import OpenAIImageGenProvider
from leagent.llm.generation.providers.siliconflow import (
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    SILICONFLOW_SIZE_CATALOG,
    SiliconFlowImageProvider,
    SiliconFlowModelFamily,
    build_payload,
    match_model_family,
    snap_image_size,
)

__all__ = [
    "DEFAULT_ENDPOINT",
    "DEFAULT_MODEL",
    "SILICONFLOW_SIZE_CATALOG",
    "DashScopeWanxProvider",
    "ImageGenResult",
    "OpenAIImageGenProvider",
    "ProviderResult",
    "SiliconFlowImageProvider",
    "SiliconFlowModelFamily",
    "build_payload",
    "match_model_family",
    "snap_image_size",
]
