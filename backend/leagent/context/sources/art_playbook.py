"""Art-playbook context source — injects the game-art pipeline playbook.

Gated so it only renders for art-flavoured requests (keyword heuristic on the
query, an explicit harness flag, or an art-like workflow hint). Keeps the system
prompt lean for non-art turns while giving art tasks the ontology, the live
node catalog, the TPL-ART-01 pattern, and the required tool sequence.
"""

from __future__ import annotations

import structlog

from leagent.prompts.art_playbook import render_art_playbook, should_attach_art_playbook
from leagent.context.sources import SOURCE_REGISTRY
from leagent.context.sources.base import ResolveContext
from leagent.context.types import ContextBlock, ContextScope, RenderTarget

logger = structlog.get_logger(__name__)


class ArtPlaybookSource:
    """Surfaces the game-art pipeline playbook for art requests."""

    id: str = "art_playbook"
    kind: str = "identity"
    scope: ContextScope = ContextScope.TURN
    priority: int = 1200
    weight: float = 1.0
    render_target: RenderTarget = RenderTarget.SYSTEM

    def invalidation_key(self, ctx: ResolveContext) -> str:
        attached = should_attach_art_playbook(
            ctx.query,
            workflow_hint=ctx.workflow_hint,
            template_vars=ctx.template_vars,
        )
        return f"art_playbook:{attached}"

    def _is_art_turn(self, ctx: ResolveContext) -> bool:
        return should_attach_art_playbook(
            ctx.query,
            workflow_hint=ctx.workflow_hint,
            template_vars=ctx.template_vars,
        )

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            if not self._is_art_turn(ctx):
                return None
            body = render_art_playbook(_node_registry())
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
                metadata={"art": True},
            )
        except Exception:
            logger.exception("art_playbook_resolve_failed")
            return None


def _node_registry():
    try:
        from leagent.workflow.nodes import get_registry

        return get_registry()
    except Exception:  # noqa: BLE001
        return None


SOURCE_REGISTRY[ArtPlaybookSource.id] = ArtPlaybookSource
