"""Model router for tier-based LLM routing and automatic fallback."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from leagent.exceptions.llm import LLMServiceError, ModelNotFoundError

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

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        return len(self.tokenizer.encode(text))

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
                model=config.model,
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
                    model=config.model,
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
                        model=config.model,
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
                        model=config.model,
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
                    model=config.model,
                    reason="low_complexity_heuristic",
                    token_count=token_count,
                )

        # Default to tier 1 for safety
        config = self.tier_configs.get(ModelTier.TIER1.value)
        if config:
            return RoutingDecision(
                tier=ModelTier.TIER1,
                provider=config.provider,
                model=config.model,
                reason="default_tier",
                token_count=token_count,
            )

        # No tiers configured - return tier2 as fallback
        config = self.tier_configs.get(ModelTier.TIER2.value)
        if config:
            return RoutingDecision(
                tier=ModelTier.TIER2,
                provider=config.provider,
                model=config.model,
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

        # Try primary provider
        try:
            provider = self.registry.get_provider(decision.provider)
            temperature, max_tokens, tool_choice, extra = self._split_provider_completion_kwargs(
                kwargs,
                default_temperature=config.temperature,
                default_max_tokens=config.max_tokens,
            )
            response = await provider.complete(
                messages=messages,
                model=decision.model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
                **extra,
            )
            return response, decision

        except (LLMServiceError, ModelNotFoundError) as e:
            # Try fallback if configured
            if config.fallback_tier:
                return await self._fallback_complete(
                    messages=messages,
                    original_decision=decision,
                    fallback_tier=config.fallback_tier,
                    tools=tools,
                    original_error=e,
                    **kwargs,
                )
            raise

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
            model=fallback_config.model,
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
                model=fallback_config.model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
                **extra,
            )
            return response, fallback_decision

        except Exception as fallback_error:
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
