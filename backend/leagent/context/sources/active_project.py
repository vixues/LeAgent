"""Active project context source.

Renders a tiny ``<active_project>`` block whenever the current turn
is bound to a code-project folder (i.e. ``ToolContext.extra``
carries ``project_roots``). The LLM picks up the absolute path and
stops asking the user for it before invoking ``coding_agent`` /
``project_*`` tools.

Intentionally lightweight: no filesystem walk, no git probing —
those belong to ``project_memory`` and the project tools. We just
echo what the chat layer already validated and pinned for this
request.
"""

from __future__ import annotations

import structlog

from leagent.context.sources import SOURCE_REGISTRY
from leagent.context.sources.base import ContextSource, ResolveContext
from leagent.context.types import ContextBlock, ContextScope, RenderTarget

logger = structlog.get_logger(__name__)


class ActiveProjectSource:
    """Surface the active project root(s) in the system prompt."""

    id: str = "active_project"
    kind: str = "identity"
    scope: ContextScope = ContextScope.SESSION
    priority: int = 750  # just above project_memory so it lands first
    weight: float = 0.95
    render_target: RenderTarget = RenderTarget.SYSTEM

    def invalidation_key(self, ctx: ResolveContext) -> str:
        joined = "|".join(ctx.project_roots or [])
        return f"active_project:{joined}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        roots = [r for r in (ctx.project_roots or []) if r]
        if not roots:
            return None
        primary = roots[0]
        lines: list[str] = [
            "<active_project>",
            f"root: {primary}",
        ]
        if len(roots) > 1:
            for extra in roots[1:]:
                lines.append(f"additional_root: {extra}")
        lines.extend(
            [
                "Use the project_* tools and coding_agent against this root.",
                "Pass `project_path` arguments as this exact absolute path when",
                "the LLM API requires them.",
                "</active_project>",
            ]
        )
        body = "\n".join(lines)
        return ContextBlock(
            source_id=self.id,
            kind=self.kind,
            render_target=self.render_target,
            body=body,
            tokens=ContextBlock.approx_tokens(body),
            cost=ContextBlock.approx_tokens(body),
            signature=ContextBlock.content_signature(self.id, body),
            priority=self.priority,
            weight=self.weight,
            metadata={
                "primary_root": primary,
                "root_count": len(roots),
                "cache_boundary": True,
            },
        )


SOURCE_REGISTRY[ActiveProjectSource.id] = ActiveProjectSource
