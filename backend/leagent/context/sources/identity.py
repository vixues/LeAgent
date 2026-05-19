"""Identity context source — persona / system-prompt body."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import structlog

from leagent.context.sources import SOURCE_REGISTRY
from leagent.context.sources.base import ContextSource, ResolveContext
from leagent.context.types import ContextBlock, ContextScope, RenderTarget

logger = structlog.get_logger(__name__)

_TEMPLATE_VAR = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def _substitute(body: str, variables: dict[str, Any]) -> str:
    if not body or not variables:
        return body

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = variables.get(key)
        return "" if value is None else str(value)

    return _TEMPLATE_VAR.sub(_replace, body)


class IdentitySource:
    """Resolves the agent's persona body from the prompt template registry."""

    id: str = "identity"
    kind: str = "identity"
    scope: ContextScope = ContextScope.PROCESS
    priority: int = 2000
    weight: float = 1.0
    render_target: RenderTarget = RenderTarget.SYSTEM

    def invalidation_key(self, ctx: ResolveContext) -> str:
        return f"identity:{ctx.variant}:{ctx.template_variant}:{ctx.persona_override[:50]}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            if ctx.persona_override:
                source = ctx.persona_override
            else:
                if ctx.prompt_registry is None:
                    logger.warning("identity_resolve_no_registry")
                    return None
                template = ctx.prompt_registry.get(ctx.variant, ctx.template_variant)
                source = template.body

            variables: dict[str, Any] = {
                "agent_name": ctx.agent_id,
                "current_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                **ctx.template_vars,
            }
            body = _substitute(source, variables)
            if not body.strip():
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
                metadata={
                    "variant": f"{ctx.variant}:{ctx.template_variant}",
                    "overridden": bool(ctx.persona_override),
                },
            )
        except Exception:
            logger.exception("identity_resolve_failed")
            return None


SOURCE_REGISTRY[IdentitySource.id] = IdentitySource
