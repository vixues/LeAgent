"""High-level LLM service combining registry, router, and providers."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, AsyncIterator, Literal, TypeVar  # noqa: F401

from leagent.config.settings import get_settings
from leagent.exceptions.llm import (
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
)
from leagent.llm.base import (
    ChatMessage,
    EmbeddingResponse,
    LLMResponse,
    MessageRole,
    StreamChunk,
    ToolCall,
    ToolDefinition,
)
from leagent.llm.registry import ProviderRegistry, create_default_registry
from leagent.llm.router import ModelRouter, ModelTier, RoutingDecision
import structlog

if TYPE_CHECKING:
    from leagent.llm.base import LLMProvider

logger = structlog.get_logger(__name__)

_TRANSIENT_RETRY_ATTEMPTS = 3
_TRANSIENT_RETRY_BASE_DELAY_SEC = 0.5
_T = TypeVar("_T")


def _is_retryable_llm_error(exc: Exception) -> bool:
    if isinstance(exc, (LLMRateLimitError, LLMTimeoutError)):
        return True
    if not isinstance(exc, LLMServiceError):
        return False
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "server error",
            "request failed",
            "max retries exceeded",
            "502",
            "503",
            "504",
            "temporarily unavailable",
        )
    )


async def _with_transient_retries(
    operation: Callable[[], Awaitable[_T]],
    *,
    operation_name: str,
) -> _T:
    last_exc: Exception | None = None
    from leagent_core.telemetry.otel import get_tracer

    tracer = get_tracer("leagent.llm.service")
    with tracer.start_as_current_span(operation_name) as span:
        if hasattr(span, "set_attribute"):
            span.set_attribute("llm.operation", operation_name)
            span.set_attribute("llm.max_attempts", _TRANSIENT_RETRY_ATTEMPTS)
        for attempt in range(_TRANSIENT_RETRY_ATTEMPTS):
            try:
                result = await operation()
                if hasattr(span, "set_attribute"):
                    span.set_attribute("llm.attempts", attempt + 1)
                return result
            except Exception as exc:
                if (
                    not _is_retryable_llm_error(exc)
                    or attempt == _TRANSIENT_RETRY_ATTEMPTS - 1
                ):
                    if hasattr(span, "record_exception"):
                        span.record_exception(exc)
                    raise
                last_exc = exc
                delay = _TRANSIENT_RETRY_BASE_DELAY_SEC * (2 ** attempt)
                if isinstance(exc, LLMRateLimitError) and exc.retry_after is not None:
                    delay = max(delay, float(exc.retry_after))
                logger.warning(
                    "llm_transient_retry",
                    operation=operation_name,
                    attempt=attempt + 1,
                    delay_sec=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)
    raise LLMServiceError(f"Transient retry failed: {last_exc}")


class LLMService:
    """High-level LLM service with routing and fallback.

    Combines:
    - ProviderRegistry: Manages multiple LLM providers
    - ModelRouter: Routes requests to appropriate tiers
    - Automatic fallback: Falls back to secondary providers on failure

    Usage:
        # From settings
        service = LLMService.from_settings()

        # Manual configuration
        service = LLMService(registry, router)

        # Completion with auto-routing
        response = await service.complete(messages)

        # Explicit tier
        response = await service.complete(messages, tier="tier1")

        # Streaming
        async for chunk in service.stream(messages):
            print(chunk.content)

        # Embeddings
        embeddings = await service.embed(["text1", "text2"])
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        router: ModelRouter,
    ) -> None:
        self.registry = registry
        self.router = router

    @classmethod
    def from_settings(cls) -> LLMService:
        """Create an LLMService from application settings."""
        settings = get_settings()

        # Create registry with default providers
        registry = create_default_registry()

        # Create router
        router = ModelRouter(registry=registry)

        # Configure tiers from settings
        if settings.llm.tier1_endpoint:
            router.configure_tier(
                tier=ModelTier.TIER1.value,
                provider="tier1",
                model=settings.llm.tier1_model,
                max_tokens=settings.llm.tier1_max_tokens,
                temperature=settings.llm.tier1_temperature,
                timeout=settings.llm.tier1_timeout,
                fallback_tier=ModelTier.TIER2.value,
            )

        if settings.llm.tier2_endpoint:
            router.configure_tier(
                tier=ModelTier.TIER2.value,
                provider="tier2",
                model=settings.llm.tier2_model,
                max_tokens=settings.llm.tier2_max_tokens,
                temperature=settings.llm.tier2_temperature,
                timeout=settings.llm.tier2_timeout,
            )

        return cls(registry=registry, router=router)

    def reload(self) -> None:
        """Rebuild the registry and router from current settings + providers.yaml.

        Called after the Admin UI changes provider config so that the
        running service picks up the new default_provider without restart.
        """
        fresh = self.from_settings()
        self.registry = fresh.registry
        self.router = fresh.router

    def get_provider(self, name: str) -> LLMProvider:
        """Get a specific provider by name."""
        return self.registry.get_provider(name)

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        tier: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[ToolDefinition] | None = None,
        tool_choice: Literal["auto", "none", "required"] | str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Complete a chat conversation.

        Args:
            messages: Conversation history.
            tier: Explicit tier to use (tier1, tier2).
            provider: Explicit provider name (bypasses routing).
            model: Explicit model (only with provider).
            temperature: Override default temperature.
            max_tokens: Override default max tokens.
            tools: Available tools for function calling.
            tool_choice: How to handle tool selection.
            **kwargs: Additional provider-specific parameters.

        Returns:
            LLMResponse with completion content and/or tool calls.
        """
        # Direct provider call if specified
        if provider:
            started = time.perf_counter()
            response = await _with_transient_retries(
                lambda: self._complete_direct(
                    messages=messages,
                    provider=provider,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    tool_choice=tool_choice,
                    **kwargs,
                ),
                operation_name="llm.complete.direct",
            )
            self._record_completion_metrics(
                response,
                provider=provider,
                model=model or response.model,
                tier="direct",
                duration=time.perf_counter() - started,
            )
            return response

        # Use router for tier-based routing
        task_description = self._extract_task_description(messages)

        started = time.perf_counter()
        response, decision = await _with_transient_retries(
            lambda: self.router.complete_with_routing(
                messages=messages,
                task_description=task_description,
                explicit_tier=tier,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                tool_choice=tool_choice,
                **kwargs,
            ),
            operation_name="llm.complete.routed",
        )
        self._record_completion_metrics(
            response,
            provider=decision.provider,
            model=response.model or decision.model,
            tier=decision.tier.value,
            duration=time.perf_counter() - started,
        )

        return response

    def _record_completion_metrics(
        self,
        response: LLMResponse,
        *,
        provider: str,
        model: str,
        tier: str,
        duration: float,
    ) -> None:
        try:
            from leagent.utils.metrics import get_metrics

            usage = response.usage
            get_metrics().record_llm_request(
                provider or "unknown",
                model or "unknown",
                tier or "default",
                duration,
                int(getattr(usage, "prompt_tokens", 0) or 0),
                int(getattr(usage, "completion_tokens", 0) or 0),
            )
        except Exception:  # noqa: BLE001
            logger.debug("llm_prometheus_metrics_failed")

    async def _complete_direct(
        self,
        messages: list[ChatMessage],
        provider: str,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
        tools: list[ToolDefinition] | None,
        tool_choice: Literal["auto", "none", "required"] | str | None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Complete using a specific provider directly."""
        provider_instance = self.registry.get_provider(provider)

        completion_model = model or provider_instance._get_default_model()
        completion_temp = temperature if temperature is not None else 0.1
        completion_max = max_tokens if max_tokens is not None else 4096

        return await provider_instance.complete(
            messages=messages,
            model=completion_model,
            temperature=completion_temp,
            max_tokens=completion_max,
            tools=tools,
            tool_choice=tool_choice,
            **kwargs,
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        tier: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[ToolDefinition] | None = None,
        tool_choice: Literal["auto", "none", "required"] | str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a chat completion.

        Args:
            messages: Conversation history.
            tier: Explicit tier to use.
            provider: Explicit provider name.
            model: Explicit model.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.
            tools: Available tools.
            tool_choice: How to handle tool selection.
            **kwargs: Additional parameters.

        Yields:
            StreamChunk objects as they arrive.
        """
        # Determine provider and model
        if provider:
            provider_instance = self.registry.get_provider(provider)
            streaming_model = model or provider_instance._get_default_model()
        else:
            task_description = self._extract_task_description(messages)
            decision = self.router.route(task_description, messages, tier)
            provider_instance = self.registry.get_provider(decision.provider)
            streaming_model = decision.model

        # Get tier config for defaults
        tier_config = self.router.get_tier_config(tier or "tier1")
        streaming_temp = temperature if temperature is not None else (tier_config.temperature if tier_config else 0.1)
        streaming_max = max_tokens if max_tokens is not None else (tier_config.max_tokens if tier_config else 4096)

        async for chunk in provider_instance.stream(
            messages=messages,
            model=streaming_model,
            temperature=streaming_temp,
            max_tokens=streaming_max,
            tools=tools,
            tool_choice=tool_choice,
            **kwargs,
        ):
            yield chunk

    async def embed(
        self,
        texts: list[str],
        *,
        provider: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResponse:
        """Generate embeddings for texts.

        Args:
            texts: List of texts to embed.
            provider: Provider to use (defaults to "embedding").
            model: Embedding model.
            **kwargs: Additional parameters.

        Returns:
            EmbeddingResponse with embedding vectors.
        """
        embed_provider = provider or "embedding"

        if not self.registry.has_provider(embed_provider):
            # Fall back to tier1/tier2 if they support embeddings
            for fallback in ["tier1", "tier2", "openai"]:
                if self.registry.has_provider(fallback):
                    provider_info = self.registry.get_provider_info(fallback)
                    if provider_info.provider.supports_embeddings:
                        embed_provider = fallback
                        break
            else:
                raise LLMServiceError(
                    "No provider available for embeddings",
                    details={"requested": provider, "available": self.registry.list_providers()},
                )

        provider_instance = self.registry.get_provider(embed_provider)
        return await provider_instance.embed(texts, model=model, **kwargs)

    async def health_check(self) -> dict[str, bool]:
        """Check health of all registered providers.

        Returns:
            Dictionary mapping provider names to health status.
        """
        results = await self.registry.test_all_connections()
        return {r.provider_name: r.is_healthy for r in results}

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return self.registry.list_providers()

    def list_tiers(self) -> list[str]:
        """List all configured tiers."""
        return self.router.list_tiers()

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return self.router.count_tokens(text)

    def count_message_tokens(self, messages: list[ChatMessage]) -> int:
        """Count tokens in messages."""
        return self.router.count_message_tokens(messages)

    async def chat(
        self,
        messages: list[dict] | list[ChatMessage],
        *,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        temperature: float | None = None,
        model_tier: str | None = None,
        **kwargs: Any,
    ) -> dict:
        """Chat method compatible with AgentController's call signature.

        Accepts messages as either ``list[dict]`` (OpenAI format from
        ``ConversationContext.to_messages()``) or ``list[ChatMessage]``,
        and accepts raw OpenAI function-calling tool schemas.

        Returns a dict with ``content``, ``tool_calls``, and ``stop_reason``
        as expected by ``AgentController._call_llm``.
        """
        # Convert dict messages to ChatMessage objects
        chat_messages: list[ChatMessage] = []
        for msg in messages:
            if isinstance(msg, ChatMessage):
                chat_messages.append(msg)
            elif isinstance(msg, dict):
                role_value = msg.get("role", "user")
                try:
                    role = MessageRole(role_value)
                except ValueError:
                    role = MessageRole.USER

                tool_calls_raw = msg.get("tool_calls")
                tool_calls: list[ToolCall] | None = None
                if tool_calls_raw:
                    tool_calls = [
                        ToolCall(
                            id=tc.get("id", ""),
                            name=tc.get("function", {}).get("name", ""),
                            arguments=tc.get("function", {}).get("arguments", "{}"),
                        )
                        for tc in tool_calls_raw
                    ]

                rc = msg.get("reasoning_content")
                reasoning = rc if isinstance(rc, str) and rc.strip() else None
                chat_messages.append(
                    ChatMessage(
                        role=role,
                        content=msg.get("content"),
                        reasoning_content=reasoning,
                        name=msg.get("name"),
                        tool_calls=tool_calls,
                        tool_call_id=msg.get("tool_call_id"),
                    )
                )

        # Convert raw OpenAI tool schemas to ToolDefinition objects
        tool_definitions: list[ToolDefinition] | None = None
        if tools:
            tool_definitions = []
            for tool in tools:
                if isinstance(tool, dict):
                    func = tool.get("function", tool)
                    tool_definitions.append(
                        ToolDefinition(
                            name=func.get("name", ""),
                            description=func.get("description", ""),
                            parameters=func.get("parameters", {}),
                        )
                    )
                elif isinstance(tool, ToolDefinition):
                    tool_definitions.append(tool)

        tier = model_tier or "tier1"
        response = await self.complete(
            chat_messages,
            tier=tier,
            temperature=temperature,
            tools=tool_definitions,
            tool_choice=tool_choice,
            **kwargs,
        )
        return response.to_agent_dict()

    async def chat_stream(
        self,
        messages: list[dict] | list[ChatMessage],
        *,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        temperature: float | None = None,
        model_tier: str | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming variant of chat() for SSE endpoints."""
        chat_messages: list[ChatMessage] = []
        for msg in messages:
            if isinstance(msg, ChatMessage):
                chat_messages.append(msg)
            elif isinstance(msg, dict):
                role_value = msg.get("role", "user")
                try:
                    role = MessageRole(role_value)
                except ValueError:
                    role = MessageRole.USER

                # The query loop emits OpenAI-shaped ``tool_calls`` on
                # assistant turns; carry them through so the next turn's
                # follow-up "tool" message is valid per OpenAI/DeepSeek
                # spec ("tool must be a response to a preceding message
                # with tool_calls").
                raw_tc = msg.get("tool_calls") or []
                parsed_tc: list[ToolCall] | None = None
                if raw_tc:
                    parsed_tc = []
                    for tc in raw_tc:
                        if not isinstance(tc, dict):
                            continue
                        fn = tc.get("function") or {}
                        parsed_tc.append(
                            ToolCall(
                                id=tc.get("id", ""),
                                name=fn.get("name", tc.get("name", "")),
                                arguments=fn.get("arguments", tc.get("arguments", "")) or "",
                            )
                        )
                    if not parsed_tc:
                        parsed_tc = None

                rc = msg.get("reasoning_content")
                reasoning = rc if isinstance(rc, str) and rc.strip() else None
                chat_messages.append(
                    ChatMessage(
                        role=role,
                        content=msg.get("content"),
                        reasoning_content=reasoning,
                        name=msg.get("name"),
                        tool_call_id=msg.get("tool_call_id"),
                        tool_calls=parsed_tc,
                    )
                )

        tool_definitions: list[ToolDefinition] | None = None
        if tools:
            tool_definitions = [
                ToolDefinition(
                    name=t.get("function", t).get("name", ""),
                    description=t.get("function", t).get("description", ""),
                    parameters=t.get("function", t).get("parameters", {}),
                )
                for t in tools
                if isinstance(t, dict)
            ]

        tier = model_tier or "tier1"
        async for chunk in self.stream(
            chat_messages,
            tier=tier,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tool_definitions,
            tool_choice=tool_choice,
            **kwargs,
        ):
            yield chunk

    def _extract_task_description(self, messages: list[ChatMessage]) -> str:
        """Extract task description from messages for routing."""
        for msg in reversed(messages):
            if msg.content:
                return msg.content[:500]  # Limit for routing
        return ""
