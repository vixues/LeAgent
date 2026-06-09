"""LLM service package with task-based model resolution."""

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
from leagent.llm.model_registry import ModelRegistry
from leagent.llm.model_spec import ModelCapabilities, ModelSpec, ModelTask, ResolvedModel
from leagent.llm.provider_plugin import (
    create_provider,
    get_provider_factory,
    list_provider_types,
    register_provider_type,
)
from leagent.llm.service import LLMService
from leagent.llm.streaming import (
    ToolCallComplete,
    ToolCallDelta,
    ToolCallStreamAssembler,
)
from leagent.llm.task_resolver import TaskResolver
from leagent.llm.transport import HttpTransport, TransportConfig, get_default_transport

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
    # Task routing
    "ModelCapabilities",
    "ModelRegistry",
    "ModelSpec",
    "ModelTask",
    "ResolvedModel",
    "TaskResolver",
    # Service
    "LLMService",
    # Transport
    "HttpTransport",
    "TransportConfig",
    "get_default_transport",
    # Streaming
    "ToolCallComplete",
    "ToolCallDelta",
    "ToolCallStreamAssembler",
    # Provider plugin
    "create_provider",
    "get_provider_factory",
    "list_provider_types",
    "register_provider_type",
]
