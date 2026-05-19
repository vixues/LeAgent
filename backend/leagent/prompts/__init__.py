"""Dedicated prompt management for the agent runtime.

System-prompt assembly flows through :class:`PromptBuilder`, which
delegates to :class:`leagent.context.ContextManager` for source-based
context gathering, cost-function budgeting, and attachments-first
rendering. The system prompt carries identity only; volatile state
(recall, working set, tool history) renders as user-role attachment
messages.
"""

from __future__ import annotations

from leagent.prompts.builder import PromptBuilder, get_prompt_builder
from leagent.prompts.context import PromptContext
from leagent.prompts.registry import PromptRegistry, get_prompt_registry
from leagent.prompts.types import (
    BuiltPrompt,
    LayerResult,
    PromptVariant,
    RenderTarget,
)

__all__ = [
    "BuiltPrompt",
    "LayerResult",
    "PromptBuilder",
    "PromptContext",
    "PromptRegistry",
    "PromptVariant",
    "RenderTarget",
    "get_prompt_builder",
    "get_prompt_registry",
]
