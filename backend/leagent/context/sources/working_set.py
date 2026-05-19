"""Context source: working set files."""

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


class WorkingSetSource:
    """Injects the current working-set file excerpts as an attachment."""

    id = "working_set"
    kind = "state"
    scope = ContextScope.TURN
    priority = 450
    weight = 0.7
    render_target = RenderTarget.ATTACHMENT_USER

    def invalidation_key(self, ctx: ResolveContext) -> str:
        return f"working_set:{id(ctx.working_set)}:{ctx.task_id}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            if ctx.working_set is None:
                return None

            entries = ctx.working_set.entries()
            if not entries:
                return None

            parts: list[str] = []
            for entry in entries:
                lines = [f"### {entry.path}"]
                if entry.excerpt_head:
                    lines.append(entry.excerpt_head)
                if entry.excerpt_tail and entry.excerpt_tail != entry.excerpt_head:
                    lines.append("...")
                    lines.append(entry.excerpt_tail)
                parts.append("\n".join(lines))

            body_content = "\n\n".join(parts)

            signature = ContextBlock.content_signature(self.id, body_content)
            body = (
                f'<attachment kind="{AttachmentKind.WORKING_SET.value}"'
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
            log.warning("working_set_source_resolve_failed", exc_info=True)
            return None


SOURCE_REGISTRY["working_set"] = WorkingSetSource  # type: ignore[assignment]
