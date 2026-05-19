"""Prompt builder — delegates to :class:`ContextManager` for source-based assembly.

For callers that supply a :class:`ContextManager` via
``PromptContext.context_manager``, the builder is a thin wrapper: it
calls ``context_manager.prepare_turn()`` and wraps the result in a
:class:`BuiltPrompt`.

For callers that do NOT supply a context manager (legacy path, tests,
workflow nodes), the builder falls back to a minimal assembly using only
the prompt registry (persona + optional tool listing).
"""

from __future__ import annotations

import threading
import time
from typing import Any
from uuid import uuid4

import structlog

from leagent.prompts.context import PromptContext
from leagent.prompts.registry import PromptRegistry, get_prompt_registry
from leagent.prompts.render import get_renderer
from leagent.prompts.types import (
    BuiltPrompt,
    LayerResult,
    RenderTarget,
)

logger = structlog.get_logger(__name__)


class PromptBuilder:
    """Assemble system prompts via :class:`ContextManager` or legacy fallback."""

    def __init__(
        self,
        *,
        registry: PromptRegistry | None = None,
        enable_cache_boundaries: bool = True,
    ) -> None:
        self._registry = registry or get_prompt_registry()
        self._enable_cache_boundaries = enable_cache_boundaries

    @property
    def registry(self) -> PromptRegistry:
        return self._registry

    async def build(self, context: PromptContext) -> BuiltPrompt:
        start = time.perf_counter()

        if context.context_manager is not None:
            return await self._build_via_context_manager(context, start)

        return await self._build_fallback(context, start)

    async def _build_via_context_manager(
        self, context: PromptContext, start: float
    ) -> BuiltPrompt:
        mgr = context.context_manager
        assert mgr is not None
        mgr.prompt_registry = self._registry

        turn = await mgr.prepare_turn(
            context.query,
            task_id=context.task_id or uuid4(),
            persona_override=context.persona_override,
            append_extra=context.append_extra,
            workflow_hint=context.workflow_hint,
            template_vars=context.template_vars,
        )

        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "prompt_build",
            variant=context.variant,
            total_chars=turn.built_prompt.total_chars,
            stable_hash=turn.built_prompt.stable_hash,
            duration_ms=duration_ms,
        )
        return turn.built_prompt

    async def _build_fallback(
        self, context: PromptContext, start: float
    ) -> BuiltPrompt:
        """Minimal assembly for callers without a ContextManager."""
        import re
        from datetime import datetime, timezone

        variant = self._registry.get(context.variant, context.template_variant)

        variables: dict[str, Any] = {
            "agent_name": context.agent_id,
            "current_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            **context.template_vars,
        }
        source = context.persona_override.strip() or variant.body
        _var_re = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
        body = _var_re.sub(
            lambda m: str(variables.get(m.group(1), "")), source
        )

        layers: list[LayerResult] = []
        if body.strip():
            layers.append(LayerResult(name="persona", body=body, tokens=len(body) // 3))

        if context.append_extra:
            layers.append(LayerResult(name="turn_extras", body=context.append_extra))

        renderer = get_renderer(
            context.render_target,
            enable_cache_boundaries=self._enable_cache_boundaries,
        )
        system_text, messages = renderer.render(layers)
        import hashlib
        full_hash = hashlib.sha256(system_text.encode()).hexdigest()

        built = BuiltPrompt(
            system_text=system_text,
            messages=messages,
            layers=layers,
            render_target=context.render_target,
            stable_hash=full_hash,
            full_hash=full_hash,
            total_chars=len(system_text),
            variant_key=variant.key,
        )

        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "prompt_build",
            variant=variant.key,
            total_chars=len(system_text),
            stable_hash=full_hash,
            duration_ms=duration_ms,
        )
        return built


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_singleton: PromptBuilder | None = None
_singleton_lock = threading.Lock()


def get_prompt_builder(
    *,
    registry: PromptRegistry | None = None,
    refresh: bool = False,
) -> PromptBuilder:
    global _singleton
    with _singleton_lock:
        if _singleton is None or refresh:
            resolved_registry = registry
            enable_cache = True
            if resolved_registry is None:
                try:
                    from leagent.config.settings import get_settings
                    prompt_settings = get_settings().prompt
                    if prompt_settings.templates_dir:
                        resolved_registry = get_prompt_registry(
                            templates_dir=prompt_settings.templates_dir,
                            hot_reload=prompt_settings.hot_reload,
                            refresh=True,
                        )
                    enable_cache = bool(prompt_settings.enable_cache_boundaries)
                except Exception as exc:
                    logger.debug("prompt_settings_unavailable_builder", error=str(exc))
            _singleton = PromptBuilder(
                registry=resolved_registry,
                enable_cache_boundaries=enable_cache,
            )
        return _singleton


__all__ = ["PromptBuilder", "get_prompt_builder"]
