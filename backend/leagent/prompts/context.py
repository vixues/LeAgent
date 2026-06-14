"""Runtime context passed to :class:`PromptBuilder`.

Slimmed down from the pre-rewrite version: the heavy lifting moved to
:class:`leagent.context.ContextManager`, so PromptContext now carries
only render-time knobs and an optional manager reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from leagent.prompts.types import RenderTarget

if TYPE_CHECKING:
    from leagent.context.manager import ContextManager
    from leagent.prompts.registry import PromptRegistry


@dataclass(slots=True)
class PromptContext:
    """Inputs for :meth:`PromptBuilder.build`.

    Most fields have moved onto :class:`ContextManager` or
    :class:`ResolveContext`. The fields that remain are the ones the
    builder itself needs for template resolution and rendering.
    """

    variant: str = "default_agent"
    template_variant: str = "default"
    query: str = ""
    cwd: str = "."
    persona_override: str = ""
    append_extra: str = ""
    workflow_hint: str = ""
    render_target: RenderTarget = RenderTarget.OPENAI
    template_vars: dict[str, Any] = field(default_factory=dict)
    playbook_ids: list[str] = field(default_factory=list)
    agent_id: str = "default"
    recall_limit: int = 5

    context_manager: "ContextManager | None" = None

    # Retained for callers that haven't migrated to ContextManager yet.
    tools: Any = None
    permission_context: Any = None
    agent_memory: Any = None
    session_manager: Any = None
    skills_manager: Any = None

    session_id: UUID | None = None
    user_id: UUID | None = None
    task_id: UUID | None = None
