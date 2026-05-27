"""Model router for tier-based LLM routing and automatic fallback."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from leagent.exceptions.llm import LLMServiceError, ModelNotFoundError
from leagent.llm.error_policy import classify_llm_error

if TYPE_CHECKING:
    from leagent.llm.base import ChatMessage, LLMProvider, LLMResponse, ToolDefinition
    from leagent.llm.registry import ProviderRegistry


class ModelTier(str, Enum):
    """Model capability tiers."""

    TIER1 = "tier1"  # Complex reasoning, planning, report generation
    TIER2 = "tier2"  # Simple tasks: classification, extraction, formatting


@dataclass
class TierConfig:
    """Configuration for a model tier."""

    provider: str
    model: str
    max_tokens: int = 4096
    temperature: float = 0.1
    timeout: float = 120.0
    fallback_tier: str | None = None


@dataclass
class RoutingDecision:
    """Result of routing decision."""

    tier: ModelTier
    provider: str
    model: str
    reason: str
    token_count: int = 0
    failover_from: str | None = None


@dataclass
class ModelRouter:
    """Routes requests to appropriate model tiers with automatic fallback.

    Tier-based routing:
    - Tier 1 (Complex): Planning, analysis, report generation, reasoning
    - Tier 2 (Simple): Classification, extraction, summarization, formatting

    Features:
    - Keyword-based routing
    - Token counting for context-aware decisions
    - Automatic fallback on failure
    """

    registry: ProviderRegistry
    tier_configs: dict[str, TierConfig] = field(default_factory=dict)
    failover_enabled: bool = False
    failover_chains: dict[str, list[str]] = field(default_factory=dict)
    failover_max_retries: int = 2
    model_aliases: dict[str, str] = field(default_factory=dict)

    # Keywords that trigger tier 1 (complex reasoning)
    TIER1_KEYWORDS: list[str] = field(
        default_factory=lambda: [
            "plan",
            "analyze",
            "report",
            "compare",
            "evaluate",
            "reason",
            "generate report",
            "design",
            "architect",
            "implement",
            "debug",
            "investigate",
            "complex",
            "multi-step",
        ]
    )

    # Keywords that trigger tier 2 (simple tasks)
    TIER2_KEYWORDS: list[str] = field(
        default_factory=lambda: [
            "classify",
            "extract",
            "summarize",
            "format",
            "translate",
            "tag",
            "label",
            "categorize",
            "convert",
            "simple",
            "quick",
        ]
    )

    # Token threshold for upgrading to tier 1
    TIER1_TOKEN_THRESHOLD: int = 8000
    # Token ceiling for selecting the cheaper tier on unclassified simple tasks.
    TIER2_LOW_COMPLEXITY_TOKEN_THRESHOLD: int = 1500

    def __post_init__(self) -> None:
        self._tokenizer: Any = None

    @property
    def tokenizer(self) -> Any:
        """Lazy-load tokenizer (import ``tiktoken`` on first use)."""
        if self._tokenizer is None:
            import tiktoken

            try:
                self._tokenizer = tiktoken.encoding_for_model("gpt-4o")
            except KeyError:
                self._tokenizer = tiktoken.get_encoding("cl100k_base")
        return self._tokenizer

    def configure_tier(
        self,
        tier: str,
        provider: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        timeout: float = 120.0,
        fallback_tier: str | None = None,
    ) -> None:
        """Configure a model tier."""
        self.tier_configs[tier] = TierConfig(
            provider=provider,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            fallback_tier=fallback_tier,
        )

    def configure_failover(
        self,
        *,
        enabled: bool,
        chain: list[str] | None = None,
        chains: dict[str, list[str]] | None = None,
        max_retries: int = 2,
    ) -> None:
        """Configure priority failover chains for routed requests."""
        self.failover_enabled = enabled
        self.failover_max_retries = max(0, int(max_retries))
        if chains:
            self.failover_chains = {
                str(tier): [str(provider) for provider in providers if provider]
                for tier, providers in chains.items()
            }
        elif chain:
            normalized = [str(provider) for provider in chain if provider]
            self.failover_chains = {
                ModelTier.TIER1.value: normalized,
                ModelTier.TIER2.value: normalized,
            }

    def configure_model_aliases(self, aliases: dict[str, str] | None) -> None:
        """Configure logical model aliases such as fast/reasoning/vision."""
        self.model_aliases = {
            str(alias).strip().lower(): str(model).strip()
            for alias, model in (aliases or {}).items()
            if str(alias).strip() and str(model).strip()
        }

    def resolve_model_alias(self, model: str | None) -> str | None:
        """Resolve a logical model alias to a provider-specific model ID."""
        if not model:
            return model
        key = model.strip().lower()
        return self.model_aliases.get(key, model)

    def _candidate_providers(self, decision: RoutingDecision) -> list[str]:
        """Return primary provider followed by available failover candidates."""
        candidates = [decision.provider]
        if self.failover_enabled:
            chain = self.failover_chains.get(decision.tier.value) or self.failover_chains.get("default") or []
            for provider_name in chain:
                if provider_name not in candidates:
                    candidates.append(provider_name)
        return candidates[: self.failover_max_retries + 1]

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        return len(self.tokenizer.encode(text))

    def _resolve_model_context_window(
        self,
        pc: Any,
        model: str,
    ) -> int:
        """Context window from providers.yaml, falling back to catalog presets."""
        if pc is None:
            return 0
        for entry in pc.models:
            if (entry.get("name") or "").strip() == model:
                cw = int(entry.get("context_window") or 0)
                if cw > 0:
                    return cw
        try:
            from leagent.llm.model_catalog import PROVIDER_PRESETS

            preset = PROVIDER_PRESETS.get(pc.type)
            if preset:
                for cap in preset.models:
                    if cap.name == model and cap.context_window > 0:
                        return cap.context_window
        except Exception:
            pass
        return 0

    def clamp_max_tokens(
        self,
        messages: list[ChatMessage],
        *,
        provider: str,
        model: str,
        requested: int,
    ) -> int:
        """Reduce completion tokens only when prompt + output would exceed context.

        Large-context models (e.g. DeepSeek 1M) keep the requested ``max_tokens``
        unless the combined budget would overflow the window.
        """
        if requested <= 0:
            return requested
        resolved = self.registry.resolve_provider_name(provider)
        try:
            from leagent.llm.provider_config import ProviderConfigService

            pc = ProviderConfigService().get_provider(resolved)
            context_window = self._resolve_model_context_window(pc, model)
            if context_window <= 0:
                return requested

            input_est = self.count_message_tokens(messages)
            margin = min(1024, max(128, context_window // 512))
            if input_est + requested + margin <= context_window:
                return requested

            available = context_window - input_est - margin
            if available < 256:
                available = max(256, context_window - input_est - margin)
            return min(requested, max(256, available))
        except Exception:
            return requested

    def count_message_tokens(self, messages: list[ChatMessage]) -> int:
        """Estimate tokens in a message list.

        Uses OpenAI's token counting rules as a baseline.
        """
        total = 0
        for msg in messages:
            # Base overhead per message
            total += 4
            if msg.content:
                total += self.count_tokens(msg.content)
            if msg.name:
                total += self.count_tokens(msg.name)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += self.count_tokens(tc.name)
                    total += self.count_tokens(tc.arguments)
        # Final overhead
        total += 2
        return total

    def route(
        self,
        task_description: str,
        messages: list[ChatMessage] | None = None,
        explicit_tier: str | None = None,
    ) -> RoutingDecision:
        """Determine which tier/model to use for a request.

        Args:
            task_description: Description of the task (usually last user message).
            messages: Full conversation history for token counting.
            explicit_tier: If provided, use this tier directly.

        Returns:
            RoutingDecision with tier, provider, model, and reason.
        """
        # Explicit tier override
        if explicit_tier:
            if explicit_tier not in self.tier_configs:
                raise ModelNotFoundError(f"Tier '{explicit_tier}' not configured")
            config = self.tier_configs[explicit_tier]
            return RoutingDecision(
                tier=ModelTier(explicit_tier),
                provider=config.provider,
                model=self.resolve_model_alias(config.model) or config.model,
                reason="explicit_tier",
            )

        # Count tokens if messages provided
        token_count = 0
        if messages:
            token_count = self.count_message_tokens(messages)

        # Large context → tier 1
        if token_count > self.TIER1_TOKEN_THRESHOLD:
            config = self.tier_configs.get(ModelTier.TIER1.value)
            if config:
                return RoutingDecision(
                    tier=ModelTier.TIER1,
                    provider=config.provider,
                    model=self.resolve_model_alias(config.model) or config.model,
                    reason=f"large_context ({token_count} tokens)",
                    token_count=token_count,
                )

        # Keyword-based routing
        task_lower = task_description.lower()

        # Check tier 2 keywords first (they're more specific)
        for keyword in self.TIER2_KEYWORDS:
            if re.search(rf"\b{keyword}\b", task_lower):
                config = self.tier_configs.get(ModelTier.TIER2.value)
                if config:
                    return RoutingDecision(
                        tier=ModelTier.TIER2,
                        provider=config.provider,
                        model=self.resolve_model_alias(config.model) or config.model,
                        reason=f"keyword_match: {keyword}",
                        token_count=token_count,
                    )
                break

        # Check tier 1 keywords
        for keyword in self.TIER1_KEYWORDS:
            if re.search(rf"\b{keyword}\b", task_lower):
                config = self.tier_configs.get(ModelTier.TIER1.value)
                if config:
                    return RoutingDecision(
                        tier=ModelTier.TIER1,
                        provider=config.provider,
                        model=self.resolve_model_alias(config.model) or config.model,
                        reason=f"keyword_match: {keyword}",
                        token_count=token_count,
                    )
                break

        if (
            token_count <= self.TIER2_LOW_COMPLEXITY_TOKEN_THRESHOLD
            and self._looks_low_complexity(task_description)
        ):
            config = self.tier_configs.get(ModelTier.TIER2.value)
            if config:
                return RoutingDecision(
                    tier=ModelTier.TIER2,
                    provider=config.provider,
                    model=self.resolve_model_alias(config.model) or config.model,
                    reason="low_complexity_heuristic",
                    token_count=token_count,
                )

        # Default to tier 1 for safety
        config = self.tier_configs.get(ModelTier.TIER1.value)
        if config:
            return RoutingDecision(
                tier=ModelTier.TIER1,
                provider=config.provider,
                model=self.resolve_model_alias(config.model) or config.model,
                reason="default_tier",
                token_count=token_count,
            )

        # No tiers configured - return tier2 as fallback
        config = self.tier_configs.get(ModelTier.TIER2.value)
        if config:
            return RoutingDecision(
                tier=ModelTier.TIER2,
                provider=config.provider,
                model=self.resolve_model_alias(config.model) or config.model,
                reason="fallback_only_tier",
                token_count=token_count,
            )

        raise LLMServiceError("No model tiers configured")

    def _looks_low_complexity(self, task_description: str) -> bool:
        text = (task_description or "").strip()
        if not text:
            return False
        words = re.findall(r"\w+", text)
        if len(words) > 80:
            return False
        complex_markers = (
            "```",
            "\n\n",
            "step by step",
            "end-to-end",
            "architecture",
            "production",
            "refactor",
            "migration",
            "security",
            "debug",
            "implement",
        )
        lower = text.lower()
        return not any(marker in lower for marker in complex_markers)

    @staticmethod
    def _split_provider_completion_kwargs(
        kwargs: dict[str, Any],
        *,
        default_temperature: float,
        default_max_tokens: int,
    ) -> tuple[float, int, Any, dict[str, Any]]:
        """Remove keys passed explicitly to provider.complete() so **kwargs does not duplicate them."""
        extra = dict(kwargs)
        temperature = extra.pop("temperature", default_temperature)
        max_tokens = extra.pop("max_tokens", default_max_tokens)
        tool_choice = extra.pop("tool_choice", None)
        return temperature, max_tokens, tool_choice, extra

    async def complete_with_routing(
        self,
        messages: list[ChatMessage],
        *,
        task_description: str | None = None,
        explicit_tier: str | None = None,
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> tuple[LLMResponse, RoutingDecision]:
        """Complete a request with automatic routing and fallback.

        Args:
            messages: Conversation history.
            task_description: Task description for routing (defaults to last message).
            explicit_tier: Force a specific tier.
            tools: Available tools.
            **kwargs: Additional parameters passed to provider.

        Returns:
            Tuple of (LLMResponse, RoutingDecision).
        """
        if task_description is None:
            # Use last user message as task description
            for msg in reversed(messages):
                if msg.content:
                    task_description = msg.content
                    break
            task_description = task_description or ""

        decision = self.route(task_description, messages, explicit_tier)

        # Get tier config for parameters
        config = self.tier_configs.get(decision.tier.value)
        if not config:
            raise LLMServiceError(f"Tier {decision.tier} not configured")

        errors: list[str] = []
        for provider_name in self._candidate_providers(decision):
            if not self.registry.is_provider_available(provider_name):
                errors.append(f"{provider_name}: circuit open or provider unavailable")
                continue
            attempt_decision = decision
            if provider_name != decision.provider:
                attempt_decision = RoutingDecision(
                    tier=decision.tier,
                    provider=provider_name,
                    model=self.resolve_model_alias(decision.model) or decision.model,
                    reason=f"failover_from_{decision.provider}",
                    token_count=decision.token_count,
                    failover_from=decision.provider,
                )
            try:
                provider = self.registry.get_provider(provider_name)
                temperature, max_tokens, tool_choice, extra = self._split_provider_completion_kwargs(
                    kwargs,
                    default_temperature=config.temperature,
                    default_max_tokens=config.max_tokens,
                )
                request_model = self.resolve_model_alias(attempt_decision.model) or attempt_decision.model
                max_tokens = self.clamp_max_tokens(
                    messages,
                    provider=provider_name,
                    model=request_model,
                    requested=max_tokens,
                )
                response = await provider.complete(
                    messages=messages,
                    model=request_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    tool_choice=tool_choice,
                    **extra,
                )
                self.registry.record_success(provider_name)
                return response, attempt_decision
            except Exception as e:
                classification = classify_llm_error(e)
                errors.append(f"{provider_name}: {classification.category.value}: {e}")
                if classification.counts_against_provider:
                    self.registry.record_failure(provider_name, str(e))
                if not classification.retryable:
                    raise

        # Try legacy tier fallback if configured and priority chain failed.
        if config.fallback_tier:
            return await self._fallback_complete(
                messages=messages,
                original_decision=decision,
                fallback_tier=config.fallback_tier,
                tools=tools,
                original_error=LLMServiceError("; ".join(errors) or "primary provider failed"),
                **kwargs,
            )
        raise LLMServiceError("; ".join(errors) or "No provider available for routed completion")

    async def _fallback_complete(
        self,
        messages: list[ChatMessage],
        original_decision: RoutingDecision,
        fallback_tier: str,
        tools: list[ToolDefinition] | None,
        original_error: Exception,
        **kwargs: Any,
    ) -> tuple[LLMResponse, RoutingDecision]:
        """Attempt completion with fallback tier."""
        fallback_config = self.tier_configs.get(fallback_tier)
        if not fallback_config:
            raise LLMServiceError(
                f"Fallback tier '{fallback_tier}' not configured. "
                f"Original error: {original_error}"
            )

        fallback_decision = RoutingDecision(
            tier=ModelTier(fallback_tier),
            provider=fallback_config.provider,
            model=self.resolve_model_alias(fallback_config.model) or fallback_config.model,
            reason=f"fallback_from_{original_decision.tier.value}",
            token_count=original_decision.token_count,
        )

        try:
            provider = self.registry.get_provider(fallback_config.provider)
            temperature, max_tokens, tool_choice, extra = self._split_provider_completion_kwargs(
                kwargs,
                default_temperature=fallback_config.temperature,
                default_max_tokens=fallback_config.max_tokens,
            )
            response = await provider.complete(
                messages=messages,
                model=self.resolve_model_alias(fallback_config.model) or fallback_config.model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
                **extra,
            )
            self.registry.record_success(fallback_config.provider)
            return response, fallback_decision

        except Exception as fallback_error:
            classification = classify_llm_error(fallback_error)
            if classification.counts_against_provider:
                self.registry.record_failure(fallback_config.provider, str(fallback_error))
            raise LLMServiceError(
                f"Both primary and fallback failed. "
                f"Primary error: {original_error}. "
                f"Fallback error: {fallback_error}"
            ) from fallback_error

    def get_tier_config(self, tier: str) -> TierConfig | None:
        """Get configuration for a tier."""
        return self.tier_configs.get(tier)

    def list_tiers(self) -> list[str]:
        """List all configured tiers."""
        return list(self.tier_configs.keys())
