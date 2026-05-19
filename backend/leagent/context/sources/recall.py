"""Context source: agent memory recall."""

from __future__ import annotations

import structlog

from leagent.context.sources import SOURCE_REGISTRY
from leagent.context.sources.base import ResolveContext
from leagent.context.types import (
    AttachmentKind,
    ContextBlock,
    ContextScope,
    RenderTarget,
)

logger = structlog.get_logger(__name__)


class RecallSource:
    """Injects recalled memory entries as an attachment."""

    id = "recall"
    kind = "state"
    scope = ContextScope.TURN
    priority = 500
    weight = 0.8
    render_target = RenderTarget.ATTACHMENT_USER

    def invalidation_key(self, ctx: ResolveContext) -> str:
        return f"recall:{ctx.query[:100]}:{ctx.session_id}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            handle = ctx.recall_handle

            if handle is None and ctx.agent_memory is not None and ctx.query:
                from leagent.memory.agent_memory import RecallHandle

                handle = RecallHandle(ctx.agent_memory)
                handle.start(
                    ctx.query,
                    user_id=ctx.user_id,
                    session_id=ctx.session_id,
                    limit=max(1, ctx.recall_attachment_limit),
                    file_state=ctx.file_state,
                )

            if handle is None:
                return None

            bundle = await handle.consume()
            if bundle is None or not bundle.entries:
                return None

            max_per_kind = max(2, ctx.recall_attachment_limit // 3)
            kind_counts: dict[str, int] = {}
            lines: list[str] = []

            for entry in bundle.entries:
                kind_label = getattr(entry.kind, "value", str(entry.kind))
                count = kind_counts.get(kind_label, 0)
                if count >= max_per_kind:
                    continue
                kind_counts[kind_label] = count + 1

                text = (entry.text or "").strip()
                summary = entry.metadata.get("summary", "") if hasattr(entry, "metadata") else ""
                content = text or summary
                if len(content) > 300:
                    content = content[:297] + "..."
                lines.append(f"- [{kind_label}] {content}")

            if not lines:
                return None

            body_content = "\n".join(lines)
            signature = ContextBlock.content_signature(self.id, body_content)
            body = (
                f'<attachment kind="{AttachmentKind.RECALL.value}"'
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
            logger.warning("recall_source_resolve_failed", exc_info=True)
            return None


SOURCE_REGISTRY["recall"] = RecallSource
