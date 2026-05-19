"""Base classes for LLM providers."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Literal

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Chat message roles."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """Represents a tool/function call from the LLM."""

    id: str
    name: str
    arguments: str  # JSON string


class ChatMessage(BaseModel):
    """A single message in a chat conversation."""

    role: MessageRole
    content: str | None = None
    # Qwen / DashScope "thinking" mode and similar APIs require echoing this
    # on the assistant message when continuing multi-turn chat.
    reasoning_content: str | None = None
    name: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None

    @classmethod
    def system(cls, content: str) -> ChatMessage:
        return cls(role=MessageRole.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str, name: str | None = None) -> ChatMessage:
        return cls(role=MessageRole.USER, content=content, name=name)

    @classmethod
    def assistant(
        cls,
        content: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        reasoning_content: str | None = None,
    ) -> ChatMessage:
        return cls(
            role=MessageRole.ASSISTANT,
            content=content,
            tool_calls=tool_calls,
            reasoning_content=reasoning_content,
        )

    @classmethod
    def tool(cls, content: str, tool_call_id: str) -> ChatMessage:
        return cls(role=MessageRole.TOOL, content=content, tool_call_id=tool_call_id)

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI API message format."""
        msg: dict[str, Any] = {"role": self.role.value}
        if self.content is not None:
            msg["content"] = self.content
        if self.name:
            msg["name"] = self.name
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.reasoning_content:
            msg["reasoning_content"] = self.reasoning_content
        return msg


class ToolDefinition(BaseModel):
    """OpenAI-compatible tool/function definition."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)

    def to_openai_format(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class TokenUsage:
    """Token usage statistics for a completion."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    #: DeepSeek context cache (see DeepSeek API Context Caching guide).
    prompt_cache_hit_tokens: int = 0
    prompt_cache_miss_tokens: int = 0


def token_usage_to_api_dict(u: TokenUsage) -> dict[str, int]:
    """Flatten usage for SSE / ``AgentResponse.token_usage`` (ints only)."""
    out: dict[str, int] = {
        "prompt_tokens": int(u.prompt_tokens),
        "completion_tokens": int(u.completion_tokens),
        "total_tokens": int(u.total_tokens),
        "reasoning_tokens": int(u.reasoning_tokens),
    }
    if u.prompt_cache_hit_tokens:
        out["prompt_cache_hit_tokens"] = int(u.prompt_cache_hit_tokens)
    if u.prompt_cache_miss_tokens:
        out["prompt_cache_miss_tokens"] = int(u.prompt_cache_miss_tokens)
    return out


@dataclass
class LLMResponse:
    """Response from an LLM completion request."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    stop_reason: str = "end_turn"   # "end_turn" | "tool_use" | "max_tokens" | "stop_sequence"
    model: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw_response: dict[str, Any] = field(default_factory=dict)
    reasoning_content: str | None = None

    def __post_init__(self) -> None:
        # Synchronize stop_reason with finish_reason for consistent access
        if self.finish_reason == "tool_calls" and self.stop_reason == "end_turn":
            self.stop_reason = "tool_use"
        elif self.finish_reason == "stop" and self.stop_reason == "end_turn":
            self.stop_reason = "end_turn"

    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    def to_message(self) -> ChatMessage:
        """Convert response to a ChatMessage for history."""
        return ChatMessage.assistant(
            content=self.content,
            tool_calls=self.tool_calls if self.tool_calls else None,
            reasoning_content=self.reasoning_content,
        )

    def to_agent_dict(self) -> dict[str, Any]:
        """Convert to dict format expected by AgentController._call_llm."""
        return {
            "content": self.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in self.tool_calls
            ],
            "stop_reason": self.stop_reason,
            "finish_reason": self.finish_reason,
            "model": self.model,
            "usage": {
                "prompt_tokens": self.usage.prompt_tokens,
                "completion_tokens": self.usage.completion_tokens,
                "total_tokens": self.usage.total_tokens,
                "reasoning_tokens": self.usage.reasoning_tokens,
            },
        }


@dataclass
class StreamChunk:
    """A single chunk in a streaming response."""

    content: str = ""
    tool_calls_delta: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    model: str = ""
    # Optional provider-specific delta payload (e.g. DeepSeek reasoner's
    # ``reasoning_content``). Consumers can inspect without changing the
    # primary ``content`` stream.
    raw_delta: dict[str, Any] | None = None
    # Present on usage-only SSE frames when ``stream_options.include_usage`` is set.
    usage: TokenUsage | None = None


@dataclass
class EmbeddingResponse:
    """Response from an embedding request."""

    embeddings: list[list[float]]
    model: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)


class LLMProvider(abc.ABC):
    """Abstract base class for LLM providers.

    All providers must implement:
    - complete(): Single-shot completion
    - stream(): Streaming completion
    - embed(): Text embedding (optional, may raise NotImplementedError)

    Providers should handle their own retries, timeouts, and error mapping.
    """

    name: str = "base"
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_embeddings: bool = False

    @abc.abstractmethod
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        tools: list[ToolDefinition] | None = None,
        tool_choice: Literal["auto", "none", "required"] | str | None = None,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Perform a single completion request.

        Args:
            messages: Conversation history.
            model: Model identifier.
            temperature: Sampling temperature (0-2).
            max_tokens: Maximum tokens to generate.
            tools: Available tools/functions.
            tool_choice: How to handle tool calls.
            stop: Stop sequences.
            **kwargs: Provider-specific options.

        Returns:
            LLMResponse with completion content and/or tool calls.

        Raises:
            LLMServiceError: On API errors.
            LLMTimeoutError: On timeout.
            LLMRateLimitError: On rate limiting.
        """

    @abc.abstractmethod
    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        tools: list[ToolDefinition] | None = None,
        tool_choice: Literal["auto", "none", "required"] | str | None = None,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a completion response.

        Yields StreamChunk objects as they arrive from the provider.
        """
        yield StreamChunk()  # pragma: no cover

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResponse:
        """Generate embeddings for a list of texts.

        Args:
            texts: Input texts to embed.
            model: Embedding model identifier.
            **kwargs: Provider-specific options.

        Returns:
            EmbeddingResponse with embedding vectors.

        Raises:
            NotImplementedError: If provider doesn't support embeddings.
        """
        raise NotImplementedError(f"{self.name} does not support embeddings")

    async def health_check(self) -> bool:
        """Check if the provider is available and responding.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            response = await self.complete(
                messages=[ChatMessage.user("ping")],
                model=self._get_default_model(),
                max_tokens=5,
            )
            return response.content is not None
        except Exception:
            return False

    def _get_default_model(self) -> str:
        """Return the default model for health checks."""
        return "default"
