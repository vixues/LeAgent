"""Session-attachments context source.

Injects the user-uploaded file manifest into the system prompt so the
LLM knows which files are available and can reference their on-disk
paths when calling file-reading tools.
"""

from __future__ import annotations

import structlog

from leagent.context.sources import SOURCE_REGISTRY
from leagent.context.sources.base import ContextSource, ResolveContext
from leagent.context.types import ContextBlock, ContextScope, RenderTarget

logger = structlog.get_logger(__name__)


class SessionAttachmentsSource:
    """Resolves the list of session-attached files for the LLM."""

    id: str = "session_attachments"
    kind: str = "state"
    scope: ContextScope = ContextScope.TURN
    priority: int = 900
    weight: float = 1.0
    render_target: RenderTarget = RenderTarget.SYSTEM

    def invalidation_key(self, ctx: ResolveContext) -> str:
        return f"session_attachments:{ctx.session_id}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            if ctx.session_manager is None or ctx.session_id is None:
                return None

            attachments = await ctx.session_manager.list_attachments(ctx.session_id)
            if not attachments:
                return None

            body = ctx.session_manager.build_attachment_manifest(attachments)
            if not body or not body.strip():
                return None

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
                metadata={"attachment_count": len(attachments)},
            )
        except Exception:
            logger.exception("session_attachments_resolve_failed")
            return None


SOURCE_REGISTRY[SessionAttachmentsSource.id] = SessionAttachmentsSource
