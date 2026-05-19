"""Context source: recent tool invocation history."""

from __future__ import annotations

import json
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


class ToolHistorySource:
    """Injects recent tool invocations as an attachment."""

    id = "tool_history"
    kind = "state"
    scope = ContextScope.TURN
    priority = 400
    weight = 0.6
    render_target = RenderTarget.ATTACHMENT_USER

    def invalidation_key(self, ctx: ResolveContext) -> str:
        return f"tool_history:{ctx.task_id}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            if ctx.working_scratchpad is None or ctx.task_id is None:
                return None

            invocations = await ctx.working_scratchpad.tool_history(
                ctx.task_id, limit=ctx.tool_history_attachment_limit
            )
            if not invocations:
                return None

            lines: list[str] = []
            for inv in invocations:
                args_str = json.dumps(inv.arguments, default=str) if inv.arguments else ""
                status = "ok" if inv.success else "error"
                lines.append(f"- {inv.name}({args_str}) -> {status}")

            body_content = "\n".join(lines)

            signature = ContextBlock.content_signature(self.id, body_content)
            body = (
                f'<attachment kind="{AttachmentKind.TOOL_HISTORY.value}"'
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
            log.warning("tool_history_source_resolve_failed", exc_info=True)
            return None


SOURCE_REGISTRY["tool_history"] = ToolHistorySource  # type: ignore[assignment]
