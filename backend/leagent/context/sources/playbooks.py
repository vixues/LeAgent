"""Playbooks context source — attaches operational runbooks at runtime."""

from __future__ import annotations

import structlog

from leagent.context.sources import SOURCE_REGISTRY
from leagent.context.sources.base import ContextSource, ResolveContext
from leagent.context.sources.policies import _get_enabled_tool_names, _substitute
from leagent.context.types import ContextBlock, ContextScope, RenderTarget
from leagent.prompts.playbooks import playbook_ids_from_context

logger = structlog.get_logger(__name__)


class PlaybooksSource:
    """Loads playbook templates when the harness supplies ``playbook_ids``."""

    id: str = "playbooks"
    kind: str = "identity"
    scope: ContextScope = ContextScope.PROCESS
    priority: int = 950
    weight: float = 1.0
    render_target: RenderTarget = RenderTarget.SYSTEM

    def invalidation_key(self, ctx: ResolveContext) -> str:
        ids = playbook_ids_from_context(
            playbook_ids=ctx.playbook_ids,
            metadata=ctx.template_vars,
        )
        return f"playbooks:{':'.join(ids)}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            playbook_ids = playbook_ids_from_context(
                playbook_ids=ctx.playbook_ids,
                metadata=ctx.template_vars,
            )
            if not playbook_ids:
                return None
            if ctx.prompt_registry is None:
                logger.warning("playbooks_resolve_no_registry")
                return None

            variables = {
                "agent_name": ctx.agent_id,
                "cwd": ctx.cwd,
                **ctx.template_vars,
            }
            enabled_tool_names = _get_enabled_tool_names(ctx)
            bodies: list[str] = []
            attached_ids: list[str] = []

            for playbook_id in playbook_ids:
                try:
                    playbook = ctx.prompt_registry.get(
                        f"playbooks/{playbook_id}",
                        variant="default",
                    )
                except Exception:
                    logger.warning("playbook_snippet_missing", playbook=playbook_id)
                    continue

                if playbook.requires_tools and enabled_tool_names is not None:
                    if not any(t in enabled_tool_names for t in playbook.requires_tools):
                        logger.debug(
                            "playbook_skipped_missing_tools",
                            playbook=playbook_id,
                            requires=playbook.requires_tools,
                        )
                        continue

                body = _substitute(playbook.body, variables).strip()
                if body:
                    bodies.append(body)
                    attached_ids.append(playbook_id)

            if not bodies:
                return None

            body = "\n\n".join(bodies)
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
                metadata={"count": len(bodies), "playbook_ids": attached_ids},
            )
        except Exception:
            logger.exception("playbooks_resolve_failed")
            return None


SOURCE_REGISTRY[PlaybooksSource.id] = PlaybooksSource
