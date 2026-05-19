"""Context source: recently-read file paths."""

from __future__ import annotations

import structlog

from leagent.context.sources import SOURCE_REGISTRY
from leagent.context.sources.base import ContextSource, ResolveContext
from leagent.context.types import (
    AttachmentKind,
    ContextBlock,
    ContextScope,
    RenderTarget,
)

log = structlog.get_logger(__name__)


class RecentReadsSource:
    """Injects the list of recently-read file paths as an attachment."""

    id = "recent_reads"
    kind = "state"
    scope = ContextScope.TURN
    priority = 350
    weight = 0.5
    render_target = RenderTarget.ATTACHMENT_USER

    def invalidation_key(self, ctx: ResolveContext) -> str:
        return f"recent_reads:{id(ctx.file_state)}:{ctx.task_id}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            if ctx.file_state is None:
                return None

            paths = ctx.file_state.recent_paths(limit=ctx.recent_reads_attachment_limit)
            if not paths:
                return None

            lines = [f"- {p}" for p in paths]
            body_content = "\n".join(lines)

            signature = ContextBlock.content_signature(self.id, body_content)
            body = (
                f'<attachment kind="{AttachmentKind.RECENT_READS.value}"'
                f' signature="{signature}">\n'
                f"{body_content}\n"
                f"</attachment>"
            )

            return ContextBlock(
                source_id=self.id,
                kind=self.kind,
                render_target=self.render_target,
                body=body,
                tokens=ContextBlock.approx_tokens(body),
                cost=len(body),
                signature=signature,
                priority=self.priority,
                weight=self.weight,
            )
        except Exception:
            log.warning("recent_reads_source_resolve_failed", exc_info=True)
            return None


SOURCE_REGISTRY["recent_reads"] = RecentReadsSource  # type: ignore[assignment]
