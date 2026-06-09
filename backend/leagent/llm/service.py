"""High-level LLM service backed by task-based model resolution."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any, Literal, TypeVar

import structlog

from leagent.exceptions.llm import LLMRateLimitError, LLMServiceError
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
from leagent.llm.image_gen.base import ImageGenResult
from leagent.llm.model_registry import ModelRegistry
from leagent.llm.model_spec import ModelTask, ResolvedModel
from leagent.llm.provider_config import ProviderConfigService
from leagent.llm.registry import ProviderRegistry, create_default_registry
from leagent.llm.task_resolver import (
    TaskResolver,
    messages_contain_image,
    strip_image_blocks_from_messages,
)

logger = structlog.get_logger(__name__)

_TRANSIENT_RETRY_ATTEMPTS = 3
_TRANSIENT_RETRY_BASE_DELAY_SEC = 0.5
_T = TypeVar("_T")


def _tool_arguments_to_json_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "{}"
    return json.dumps(value, ensure_ascii=False)


def _coerce_task(task: ModelTask | str | None) -> ModelTask:
    if isinstance(task, ModelTask):
        return task
    if task:
        try:
            return ModelTask(str(task))
        except ValueError as exc:
            raise LLMServiceError(f"Unknown model task: {task}") from exc
    return ModelTask.CHAT


async def _with_transient_retries(
    operation: Callable[[], Awaitable[_T]],
    *,
    operation_name: str,
) -> _T:
    last_exc: Exception | None = None
    from leagent.telemetry.otel import get_tracer

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
                retryable = classify_llm_error(exc).retryable
                if not retryable or attempt == _TRANSIENT_RETRY_ATTEMPTS - 1:
                    if hasattr(span, "record_exception"):
                        span.record_exception(exc)
                    raise
                last_exc = exc
                delay = _TRANSIENT_RETRY_BASE_DELAY_SEC * (2**attempt)
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
    """Unified LLM, embedding, and image-generation service."""

    def __init__(
        self,
        registry: ProviderRegistry,
        model_registry: ModelRegistry,
        resolver: TaskResolver | None = None,
    ) -> None:
        self.registry = registry
        self.model_registry = model_registry
        self.resolver = resolver or TaskResolver(registry, model_registry)

    @classmethod
    def from_settings(cls) -> LLMService:
        """Create an LLMService from providers.yaml v2."""
        registry = create_default_registry()
        provider_config = ProviderConfigService(registry=registry)
        model_registry = provider_config.get_model_registry()
        logger.info(
            "llm_service_tasks_configured",
            registered_providers=registry.list_providers(),
            default_task=model_registry.default_task.value,
        )
        return cls(
            registry=registry,
            model_registry=model_registry,
            resolver=TaskResolver(registry, model_registry),
        )

    def reload(self) -> None:
        """Rebuild registry and model registry after provider config changes."""
        old_registry = self.registry
        fresh = self.from_settings()
        self.registry = fresh.registry
        self.model_registry = fresh.model_registry
        self.resolver = fresh.resolver
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(old_registry.aclose())
        except RuntimeError:
            pass

    def get_provider(self, name: str) -> Any:
        return self.registry.get_provider(name)

    async def aclose(self) -> None:
        await self.registry.aclose()

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        task: ModelTask | str = ModelTask.CHAT,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[ToolDefinition] | None = None,
        tool_choice: Literal["auto", "none", "required"] | str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Complete a chat conversation for a logical task."""
        resolved = self.resolver.resolve(
            _coerce_task(task),
            messages=messages,
            user_provider=provider,
            user_model=model,
        )
        messages = self._prepare_messages_for_model(messages, resolved)
        started = time.perf_counter()
        response = await _with_transient_retries(
            lambda: self._complete_resolved(
                messages=messages,
                resolved=resolved,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
                **kwargs,
            ),
            operation_name=f"llm.complete.{resolved.task.value}",
        )
        self._record_completion_metrics(
            response,
            provider=resolved.provider,
            model=response.model or resolved.model,
            task=resolved.task.value,
            duration=time.perf_counter() - started,
        )
        self._record_request_log(
            response,
            provider=resolved.provider,
            request_model=resolved.model,
            model=response.model or resolved.model,
            duration=time.perf_counter() - started,
        )
        return response

    async def _complete_resolved(
        self,
        *,
        messages: list[ChatMessage],
        resolved: ResolvedModel,
        temperature: float | None,
        max_tokens: int | None,
        tools: list[ToolDefinition] | None,
        tool_choice: Literal["auto", "none", "required"] | str | None,
        **kwargs: Any,
    ) -> LLMResponse:
        errors: list[str] = []
        for provider_name, model_name in self.resolver.candidate_providers(resolved):
            if not self.registry.is_provider_available(provider_name):
                errors.append(f"{provider_name}: circuit open or provider unavailable")
                continue
            spec = self.model_registry.get_spec(provider_name, model_name) or resolved.spec
            request_max = max_tokens if max_tokens is not None else resolved.max_tokens
            request_max = self.resolver.clamp_max_tokens(messages, spec=spec, requested=request_max)
            try:
                provider = self.registry.get_provider(provider_name)
                response = await provider.complete(
                    messages=messages,
                    model=model_name,
                    temperature=temperature if temperature is not None else resolved.temperature,
                    max_tokens=request_max,
                    tools=tools,
                    tool_choice=tool_choice,
                    **kwargs,
                )
                self.registry.record_success(provider_name)
                return response
            except Exception as exc:
                classification = classify_llm_error(exc)
                errors.append(f"{provider_name}: {classification.category.value}: {exc}")
                if classification.counts_against_provider:
                    self.registry.record_failure(provider_name, str(exc))
                if not classification.retryable:
                    raise
        raise LLMServiceError("; ".join(errors) or "No provider available for task")

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        task: ModelTask | str = ModelTask.CHAT,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[ToolDefinition] | None = None,
        tool_choice: Literal["auto", "none", "required"] | str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a chat completion for a logical task."""
        resolved = self.resolver.resolve(
            _coerce_task(task),
            messages=messages,
            user_provider=provider,
            user_model=model,
        )
        messages = self._prepare_messages_for_model(messages, resolved)
        errors: list[str] = []
        for provider_name, model_name in self.resolver.candidate_providers(resolved):
            if not self.registry.is_provider_available(provider_name):
                errors.append(f"{provider_name}: circuit open or provider unavailable")
                continue
            yielded = False
            started = time.perf_counter()
            first_chunk_at: float | None = None
            final_model = model_name
            final_usage: TokenUsage | None = None
            try:
                spec = self.model_registry.get_spec(provider_name, model_name) or resolved.spec
                request_max = max_tokens if max_tokens is not None else resolved.max_tokens
                request_max = self.resolver.clamp_max_tokens(messages, spec=spec, requested=request_max)
                provider_instance = self.registry.get_provider(provider_name)
                async for chunk in provider_instance.stream(
                    messages=messages,
                    model=model_name,
                    temperature=temperature if temperature is not None else resolved.temperature,
                    max_tokens=request_max,
                    tools=tools,
                    tool_choice=tool_choice,
                    **kwargs,
                ):
                    yielded = True
                    if first_chunk_at is None:
                        first_chunk_at = time.perf_counter()
                    if chunk.model:
                        final_model = chunk.model
                    if chunk.usage is not None:
                        final_usage = chunk.usage
                    yield chunk
                self.registry.record_success(provider_name)
                self._record_request_log(
                    LLMResponse(model=final_model, usage=final_usage or TokenUsage()),
                    provider=provider_name,
                    request_model=model_name,
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
        """Generate embeddings via the embedding task."""
        if provider and model:
            resolved_provider, resolved_model = provider, model
        else:
            resolved = self.resolver.resolve(ModelTask.EMBEDDING)
            resolved_provider, resolved_model = resolved.provider, resolved.model
        if not self.registry.has_provider(resolved_provider):
            raise LLMServiceError(
                "No provider available for embeddings",
                details={"requested": provider, "available": self.registry.list_providers()},
            )
        provider_instance = self.registry.get_provider(resolved_provider)
        return await provider_instance.embed(texts, model=resolved_model, **kwargs)

    async def generate_image(
        self,
        prompt: str,
        *,
        task: ModelTask | str = ModelTask.IMAGE_GEN,
        provider: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> ImageGenResult:
        """Generate an image via the image_gen task."""
        resolved = self.resolver.resolve(_coerce_task(task), user_provider=provider, user_model=model)
        pc = ProviderConfigService().get_provider(resolved.provider)
        if pc is None:
            raise LLMServiceError(f"Provider '{resolved.provider}' not found")
        image_provider = ProviderConfigService()._create_image_gen_provider(pc, resolved.model)
        result = await image_provider.generate(model=resolved.model, prompt=prompt, **kwargs)
        result.provider = resolved.provider
        result.model = resolved.model
        return result

    async def health_check(self) -> dict[str, bool]:
        results = await self.registry.test_all_connections()
        return {r.provider_name: r.is_healthy for r in results}

    def list_providers(self) -> list[str]:
        return self.registry.list_providers()

    def list_tasks(self) -> list[str]:
        return [task.value for task in ModelTask]

    def list_tiers(self) -> list[str]:
        """Deprecated compatibility shim: v2 exposes tasks instead."""
        return self.list_tasks()

    def count_tokens(self, text: str) -> int:
        try:
            import tiktoken

            return len(tiktoken.get_encoding("cl100k_base").encode(text))
        except Exception:
            return max(1, len(text) // 4)

    def count_message_tokens(self, messages: list[ChatMessage]) -> int:
        return sum(self.count_tokens(str(m.content or "")) for m in messages)

    async def chat(
        self,
        messages: list[dict] | list[ChatMessage],
        *,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        temperature: float | None = None,
        task: ModelTask | str = ModelTask.CHAT,
        provider: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """AgentController-compatible chat method."""
        response = await self.complete(
            self._coerce_messages(messages),
            task=task,
            provider=provider,
            model=model,
            temperature=temperature,
            tools=self._coerce_tools(tools),
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
        task: ModelTask | str = ModelTask.CHAT,
        max_tokens: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming variant of chat()."""
        async for chunk in self.stream(
            self._coerce_messages(messages),
            task=task,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=self._coerce_tools(tools),
            tool_choice=tool_choice,
            **kwargs,
        ):
            yield chunk

    def _coerce_messages(self, messages: list[dict] | list[ChatMessage]) -> list[ChatMessage]:
        out: list[ChatMessage] = []
        for msg in messages:
            if isinstance(msg, ChatMessage):
                out.append(msg)
                continue
            if not isinstance(msg, dict):
                continue
            try:
                role = MessageRole(msg.get("role", "user"))
            except ValueError:
                role = MessageRole.USER
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
                            arguments=_tool_arguments_to_json_string(
                                fn.get("arguments", tc.get("arguments", "")),
                            ),
                        )
                    )
                if not parsed_tc:
                    parsed_tc = None
            rc = msg.get("reasoning_content")
            out.append(
                ChatMessage(
                    role=role,
                    content=msg.get("content"),
                    reasoning_content=rc if isinstance(rc, str) and rc.strip() else None,
                    name=msg.get("name"),
                    tool_calls=parsed_tc,
                    tool_call_id=msg.get("tool_call_id"),
                )
            )
        return out

    def _prepare_messages_for_model(
        self,
        messages: list[ChatMessage],
        resolved: ResolvedModel,
    ) -> list[ChatMessage]:
        """Strip inline vision blocks when the resolved model is text-only."""
        if resolved.spec.capabilities.supports_input("image"):
            return messages
        if not messages_contain_image(messages):
            return messages
        return strip_image_blocks_from_messages(messages)

    def _coerce_tools(self, tools: list[dict] | None) -> list[ToolDefinition] | None:
        if not tools:
            return None
        out: list[ToolDefinition] = []
        for tool in tools:
            if isinstance(tool, ToolDefinition):
                out.append(tool)
            elif isinstance(tool, dict):
                func = tool.get("function", tool)
                out.append(
                    ToolDefinition(
                        name=func.get("name", ""),
                        description=func.get("description", ""),
                        parameters=func.get("parameters", {}),
                    )
                )
        return out

    def _record_completion_metrics(
        self,
        response: LLMResponse,
        *,
        provider: str,
        model: str,
        task: str,
        duration: float,
    ) -> None:
        try:
            from leagent.utils.metrics import get_metrics

            usage = response.usage
            get_metrics().record_llm_request(
                provider or "unknown",
                model or "unknown",
                task or "default",
                duration,
                int(getattr(usage, "prompt_tokens", 0) or 0),
                int(getattr(usage, "completion_tokens", 0) or 0),
            )
        except Exception:
            logger.debug("llm_prometheus_metrics_failed")

    def _estimate_cost_usd(self, model: str, input_tokens: int, output_tokens: int) -> float:
        try:
            from leagent.llm.model_catalog import get_default_pricing
            from leagent.llm.provider_config import ProviderConfigService

            pricing = ProviderConfigService().get_pricing_config()
            entry = pricing.get(model, {}) if isinstance(pricing, dict) else {}
            input_price = float(entry.get("input_per_1m", 0.0) or entry.get("price_input_per_1m", 0.0) or 0.0)
            output_price = float(entry.get("output_per_1m", 0.0) or entry.get("price_output_per_1m", 0.0) or 0.0)
            if input_price == 0.0 and output_price == 0.0:
                catalog_entry = get_default_pricing().get(model, {})
                input_price = float(catalog_entry.get("input_per_1m", 0.0))
                output_price = float(catalog_entry.get("output_per_1m", 0.0))
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
        try:
            usage = response.usage
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            total_cost = self._estimate_cost_usd(model, input_tokens, output_tokens)

            async def _insert() -> None:
                try:
                    from leagent.db import get_database_service
                    from leagent.db.models import LLMRequestLog

                    db = get_database_service()
                    async with db.session() as session:
                        session.add(
                            LLMRequestLog(
                                provider_name=provider or "unknown",
                                model=model or "unknown",
                                request_model=request_model or model or "unknown",
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                cache_read_tokens=int(getattr(usage, "prompt_cache_hit_tokens", 0) or 0),
                                cache_write_tokens=int(getattr(usage, "prompt_cache_miss_tokens", 0) or 0),
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


def data_url_for_image(path: str) -> str:
    """Return a base64 data URL for an image path."""
    suffix = Path(path).suffix.lower().lstrip(".") or "png"
    mime = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix}"
    raw = Path(path).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"
