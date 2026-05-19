"""LLM service package.

Provides a unified interface for multiple LLM providers with:
- Tier-based routing (tier1 for complex, tier2 for simple tasks)
- Automatic fallback on failures
- Token counting and context management
- Streaming support
- Function/tool calling
- Embeddings

Example usage:
    from leagent.llm import (
        ChatMessage,
        LLMService,
        ToolDefinition,
    )

    # Create service
    service = LLMService.from_settings()

    # Simple completion
    response = await service.complete([
        ChatMessage.user("Hello, how are you?")
    ])

    # With routing
    response = await service.complete(
        [ChatMessage.user("Analyze this complex problem...")],
        tier="tier1",
    )

    # Streaming
    async for chunk in service.stream([
        ChatMessage.user("Write a story...")
    ]):
        print(chunk.content, end="")
"""

from leagent.llm.base import (
    ChatMessage,
    EmbeddingResponse,
    LLMProvider,
    LLMResponse,
    MessageRole,
    StreamChunk,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)
from leagent.llm.registry import (
    HealthCheckResult,
    ProviderInfo,
    ProviderRegistry,
    create_default_registry,
)
from leagent.llm.router import (
    ModelRouter,
    ModelTier,
    RoutingDecision,
    TierConfig,
)
from leagent.llm.service import LLMService

__all__ = [
    # Base types
    "ChatMessage",
    "EmbeddingResponse",
    "LLMProvider",
    "LLMResponse",
    "MessageRole",
    "StreamChunk",
    "TokenUsage",
    "ToolCall",
    "ToolDefinition",
    # Registry
    "HealthCheckResult",
    "ProviderInfo",
    "ProviderRegistry",
    "create_default_registry",
    # Router
    "ModelRouter",
    "ModelTier",
    "RoutingDecision",
    "TierConfig",
    # Service
    "LLMService",
]
