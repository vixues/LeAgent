"""Prompt builder — delegates to :class:`ContextManager` for source-based assembly.

The builder is a thin wrapper over the source-driven
:class:`leagent.context.ContextManager`: it calls
``context_manager.prepare_turn()`` and wraps the result in a
:class:`BuiltPrompt`. A :class:`ContextManager` is the single, canonical
prompt-assembly path; the legacy registry-only fallback has been removed.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog

from leagent.prompts.registry import PromptRegistry, get_prompt_registry

if TYPE_CHECKING:
    from leagent.prompts.context import PromptContext
    from leagent.prompts.types import BuiltPrompt

logger = structlog.get_logger(__name__)


class PromptBuilder:
    """Assemble system prompts via the source-driven :class:`ContextManager`."""

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
        if context.context_manager is None:
            raise ValueError(
                "PromptBuilder.build requires a ContextManager. The legacy "
                "registry-only fallback has been removed; assemble prompts "
                "through leagent.context.ContextManager.prepare_turn()."
            )
        return await self._build_via_context_manager(context, time.perf_counter())

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
            playbook_ids=context.playbook_ids,
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
