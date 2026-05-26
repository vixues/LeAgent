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
    TokenUsage,
    ToolCall,
    ToolDefinition,
)
from leagent.llm.error_policy import classify_llm_error
from leagent.llm.registry import ProviderRegistry, create_default_registry
from leagent.llm.router import ModelRouter, ModelTier, RoutingDecision
import structlog

if TYPE_CHECKING:
    from leagent.llm.base import LLMProvider

logger = structlog.get_logger(__name__)

_TRANSIENT_RETRY_ATTEMPTS = 3
_TRANSIENT_RETRY_BASE_DELAY_SEC = 0.5
_T = TypeVar("_T")

_SPEND_LIMIT_CACHE_TTL_SEC = 30.0
_spend_limit_cache: dict[tuple[str, str], tuple[float, float]] = {}  # (provider, scope) → (value, monotonic_ts)


def _is_retryable_llm_error(exc: Exception) -> bool:
    return classify_llm_error(exc).retryable


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

        def _registry_model(provider_name: str, fallback: str) -> str:
            if registry.has_provider(provider_name):
                metadata = registry.get_provider_info(provider_name).metadata
                model = metadata.get("model")
                if isinstance(model, str) and model.strip():
                    return model.strip()
            return fallback

        # Configure tiers from settings, then allow providers.yaml metadata to
        # supply promoted default models.
        if settings.llm.tier1_endpoint:
            router.configure_tier(
                tier=ModelTier.TIER1.value,
                provider="tier1",
                model=_registry_model("tier1", settings.llm.tier1_model),
                max_tokens=settings.llm.tier1_max_tokens,
                temperature=settings.llm.tier1_temperature,
                timeout=settings.llm.tier1_timeout,
                fallback_tier=ModelTier.TIER2.value,
            )

        if settings.llm.tier2_endpoint:
            router.configure_tier(
                tier=ModelTier.TIER2.value,
                provider="tier2",
                model=_registry_model("tier2", settings.llm.tier2_model),
                max_tokens=settings.llm.tier2_max_tokens,
                temperature=settings.llm.tier2_temperature,
                timeout=settings.llm.tier2_timeout,
            )

        try:
            from leagent.llm.provider_config import ProviderConfigService

            provider_config = ProviderConfigService()
            routing = provider_config.get_routing_config()
            chain = routing.get("failover_chain")
            chains = routing.get("failover_chains")
            router.configure_failover(
                enabled=bool(routing.get("failover_enabled", False)),
                chain=chain if isinstance(chain, list) else None,
                chains=chains if isinstance(chains, dict) else None,
                max_retries=int(routing.get("max_retries", 2) or 2),
            )
            router.configure_model_aliases(provider_config.get_model_aliases())
        except Exception:
            logger.debug("llm_failover_config_unavailable")

        # Log final tier assignments for observability.
        tier1_cfg = router.tier_configs.get("tier1")
        tier2_cfg = router.tier_configs.get("tier2")
        logger.info(
            "llm_service_tiers_configured",
            tier1_provider=tier1_cfg.provider if tier1_cfg else None,
            tier1_model=tier1_cfg.model if tier1_cfg else None,
            tier2_provider=tier2_cfg.provider if tier2_cfg else None,
            tier2_model=tier2_cfg.model if tier2_cfg else None,
            registered_providers=registry.list_providers(),
        )

        return cls(registry=registry, router=router)

    def reload(self) -> None:
        """Rebuild the registry and router from current settings + providers.yaml.

        Called after the Admin UI changes provider config so that the
        running service picks up the new default_provider without restart.
        """
        old_registry = self.registry
        fresh = self.from_settings()
        self.registry = fresh.registry
        self.router = fresh.router
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(old_registry.aclose())
        except RuntimeError:
            pass

    def get_provider(self, name: str) -> LLMProvider:
        """Get a specific provider by name."""
        return self.registry.get_provider(name)

    async def aclose(self) -> None:
        """Release provider-level resources such as pooled HTTP clients."""
        await self.registry.aclose()

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
            await self._enforce_spend_limits(provider)
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
            self._record_request_log(
                response,
                provider=provider,
                request_model=model or response.model,
                model=model or response.model,
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
        self._record_request_log(
            response,
            provider=decision.provider,
            request_model=decision.model,
            model=response.model or decision.model,
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

    async def _enforce_spend_limits(self, provider: str) -> None:
        """Block explicit provider calls that exceed configured spend limits.

        Results are cached in-memory for ``_SPEND_LIMIT_CACHE_TTL_SEC`` to
        avoid running aggregate DB queries on every LLM call.
        """
        try:
            from datetime import datetime
            from sqlmodel import func, select

            from leagent.llm.provider_config import ProviderConfigService
            from leagent.services.database import get_database_service
            from leagent.services.database.models import LLMRequestLog

            pc = ProviderConfigService().get_provider(provider)
            limits = pc.metadata.get("limits") if pc and isinstance(pc.metadata, dict) else {}
            if not isinstance(limits, dict) or not limits:
                return
            daily_limit = limits.get("daily_usd")
            monthly_limit = limits.get("monthly_usd")
            if daily_limit in (None, "") and monthly_limit in (None, ""):
                return

            now_mono = time.monotonic()

            async def _cached_spend(scope: str) -> float:
                key = (provider, scope)
                cached = _spend_limit_cache.get(key)
                if cached is not None:
                    value, ts = cached
                    if now_mono - ts < _SPEND_LIMIT_CACHE_TTL_SEC:
                        return value

                now = datetime.utcnow()
                if scope == "daily":
                    cutoff = datetime(now.year, now.month, now.day)
                else:
                    cutoff = datetime(now.year, now.month, 1)

                db = get_database_service()
                async with db.session() as session:
                    total = (
                        await session.exec(
                            select(func.coalesce(func.sum(LLMRequestLog.total_cost_usd), 0.0))
                            .where(LLMRequestLog.provider_name == provider)
                            .where(LLMRequestLog.created_at >= cutoff)
                        )
                    ).one()
                result = float(total or 0.0)
                _spend_limit_cache[key] = (result, now_mono)
                return result

            if daily_limit not in (None, ""):
                daily = await _cached_spend("daily")
                if daily >= float(daily_limit):
                    raise LLMServiceError(f"Provider '{provider}' daily spend limit exceeded")
            if monthly_limit not in (None, ""):
                monthly = await _cached_spend("monthly")
                if monthly >= float(monthly_limit):
                    raise LLMServiceError(f"Provider '{provider}' monthly spend limit exceeded")
        except LLMServiceError:
            raise
        except Exception:
            logger.debug("llm_spend_limit_check_failed")

    def _estimate_cost_usd(self, model: str, input_tokens: int, output_tokens: int) -> float:
        try:
            from leagent.llm.provider_config import PROVIDER_PRESETS, ProviderConfigService

            pricing = ProviderConfigService().get_pricing_config()
            entry = pricing.get(model, {}) if isinstance(pricing, dict) else {}
            input_price = float(entry.get("input_per_1m", 0.0) or entry.get("price_input_per_1m", 0.0) or 0.0)
            output_price = float(entry.get("output_per_1m", 0.0) or entry.get("price_output_per_1m", 0.0) or 0.0)
            if input_price == 0.0 and output_price == 0.0:
                for preset in PROVIDER_PRESETS.values():
                    for preset_model in preset.get("models", []):
                        if preset_model.get("name") == model:
                            input_price = float(preset_model.get("price_input_per_1m", 0.0) or 0.0)
                            output_price = float(preset_model.get("price_output_per_1m", 0.0) or 0.0)
                            break
                    if input_price or output_price:
                        break
            return (input_tokens / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)
        except Exception:
            return 0.0

    def _record_request_log(
        self,
        response: LLMResponse,
        *,
        provider: str,
        request_model: str,
        model: str,
        duration: float,
        is_streaming: bool = False,
        ttfb_ms: float = 0.0,
        status_code: int = 200,
        error: str | None = None,
    ) -> None:
        """Best-effort async persistence for request-level usage logs."""
        try:
            usage = response.usage
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            cache_read = int(getattr(usage, "prompt_cache_hit_tokens", 0) or 0)
            cache_write = int(getattr(usage, "prompt_cache_miss_tokens", 0) or 0)
            total_cost = self._estimate_cost_usd(model, input_tokens, output_tokens)

            async def _insert() -> None:
                try:
                    from leagent.services.database import get_database_service
                    from leagent.services.database.models import LLMRequestLog

                    db = get_database_service()
                    async with db.session() as session:
                        session.add(
                            LLMRequestLog(
                                provider_name=provider or "unknown",
                                model=model or "unknown",
                                request_model=request_model or model or "unknown",
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                cache_read_tokens=cache_read,
                                cache_write_tokens=cache_write,
                                total_cost_usd=total_cost,
                                latency_ms=duration * 1000,
                                ttfb_ms=ttfb_ms,
                                status_code=status_code,
                                error=error,
                                is_streaming=is_streaming,
                            )
                        )
                except Exception:
                    logger.debug("llm_request_log_insert_failed")

            asyncio.create_task(_insert())
        except Exception:
            logger.debug("llm_request_log_schedule_failed")

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

        completion_model = self.router.resolve_model_alias(model) if model else None
        completion_model = completion_model or provider_instance._get_default_model()
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
            streaming_model = self.router.resolve_model_alias(model) if model else None
            streaming_model = streaming_model or provider_instance._get_default_model()

            tier_config = self.router.get_tier_config(tier or "tier1")
            streaming_temp = temperature if temperature is not None else (tier_config.temperature if tier_config else 0.1)
            streaming_max = max_tokens if max_tokens is not None else (tier_config.max_tokens if tier_config else 4096)
            started = time.perf_counter()
            first_chunk_at: float | None = None
            final_model = streaming_model
            final_usage: TokenUsage | None = None
            async for chunk in provider_instance.stream(
                messages=messages,
                model=streaming_model,
                temperature=streaming_temp,
                max_tokens=streaming_max,
                tools=tools,
                tool_choice=tool_choice,
                **kwargs,
            ):
                if first_chunk_at is None:
                    first_chunk_at = time.perf_counter()
                    try:
                        from leagent.utils.metrics import get_metrics

                        get_metrics().record_llm_stream_ttfb(
                            provider,
                            streaming_model,
                            tier or "tier1",
                            first_chunk_at - started,
                        )
                    except Exception:
                        logger.debug("llm_stream_ttfb_metrics_failed")
                try:
                    from leagent.utils.metrics import get_metrics

                    get_metrics().llm_streaming_chunks_total.labels(
                        provider=provider,
                        model=streaming_model,
                    ).inc()
                except Exception:
                    logger.debug("llm_stream_chunk_metrics_failed")
                if chunk.model:
                    final_model = chunk.model
                if chunk.usage is not None:
                    final_usage = chunk.usage
                yield chunk
            self.registry.record_success(provider)
            self._record_request_log(
                LLMResponse(model=final_model, usage=final_usage or TokenUsage()),
                provider=provider,
                request_model=streaming_model,
                model=final_model,
                duration=time.perf_counter() - started,
                is_streaming=True,
                ttfb_ms=((first_chunk_at - started) * 1000) if first_chunk_at is not None else 0.0,
            )
            return

        task_description = self._extract_task_description(messages)
        decision = self.router.route(task_description, messages, tier)
        tier_config = self.router.get_tier_config(decision.tier.value)
        streaming_temp = temperature if temperature is not None else (tier_config.temperature if tier_config else 0.1)
        streaming_max = max_tokens if max_tokens is not None else (tier_config.max_tokens if tier_config else 4096)
        errors: list[str] = []

        for provider_name in self.router._candidate_providers(decision):
            if not self.registry.is_provider_available(provider_name):
                errors.append(f"{provider_name}: circuit open or provider unavailable")
                continue
            yielded = False
            try:
                provider_instance = self.registry.get_provider(provider_name)
                request_model = self.router.resolve_model_alias(decision.model) or decision.model
                started = time.perf_counter()
                first_chunk_at = None
                final_model = request_model
                final_usage = None
                async for chunk in provider_instance.stream(
                    messages=messages,
                    model=request_model,
                    temperature=streaming_temp,
                    max_tokens=streaming_max,
                    tools=tools,
                    tool_choice=tool_choice,
                    **kwargs,
                ):
                    yielded = True
                    if first_chunk_at is None:
                        first_chunk_at = time.perf_counter()
                        try:
                            from leagent.utils.metrics import get_metrics

                            get_metrics().record_llm_stream_ttfb(
                                provider_name,
                                request_model,
                                decision.tier.value,
                                first_chunk_at - started,
                            )
                        except Exception:
                            logger.debug("llm_stream_ttfb_metrics_failed")
                    try:
                        from leagent.utils.metrics import get_metrics

                        get_metrics().llm_streaming_chunks_total.labels(
                            provider=provider_name,
                            model=request_model,
                        ).inc()
                    except Exception:
                        logger.debug("llm_stream_chunk_metrics_failed")
                    if chunk.model:
                        final_model = chunk.model
                    if chunk.usage is not None:
                        final_usage = chunk.usage
                    yield chunk
                self.registry.record_success(provider_name)
                self._record_request_log(
                    LLMResponse(model=final_model, usage=final_usage or TokenUsage()),
                    provider=provider_name,
                    request_model=decision.model,
                    model=final_model,
                    duration=time.perf_counter() - started,
                    is_streaming=True,
                    ttfb_ms=((first_chunk_at - started) * 1000) if first_chunk_at is not None else 0.0,
                )
                return
            except Exception as exc:
                classification = classify_llm_error(exc)
                if classification.counts_against_provider:
                    self.registry.record_failure(provider_name, str(exc))
                errors.append(f"{provider_name}: {classification.category.value}: {exc}")
                if yielded or not classification.retryable:
                    raise

        raise LLMServiceError("; ".join(errors) or "No provider available for routed stream")

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
