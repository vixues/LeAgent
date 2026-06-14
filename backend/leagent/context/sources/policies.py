"""Policies context source — concatenates variant policy snippets."""

from __future__ import annotations

import re
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


def _get_enabled_tool_names(ctx: ResolveContext) -> set[str] | None:
    """Return set of enabled tool names from context, or None if tools unavailable."""
    if ctx.tools is None:
        return None
    try:
        enabled = ctx.tools.get_enabled_tools()
        names: set[str] = set()
        for tool in enabled:
            names.add(tool.name)
            for alias in getattr(tool, "aliases", None) or []:
                names.add(alias)
        return names
    except Exception:
        return None


class PoliciesSource:
    """Loads and concatenates policy templates referenced by the active variant."""

    id: str = "policies"
    kind: str = "identity"
    scope: ContextScope = ContextScope.PROCESS
    priority: int = 1000
    weight: float = 1.0
    render_target: RenderTarget = RenderTarget.SYSTEM

    def invalidation_key(self, ctx: ResolveContext) -> str:
        return f"policies:{ctx.variant}:{ctx.template_variant}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            if ctx.prompt_registry is None:
                logger.warning("policies_resolve_no_registry")
                return None

            variant = ctx.prompt_registry.get(ctx.variant, ctx.template_variant)
            if not variant.policies:
                return None

            variables: dict[str, Any] = {
                "agent_name": ctx.agent_id,
                "cwd": ctx.cwd,
                **ctx.template_vars,
            }

            enabled_tool_names = _get_enabled_tool_names(ctx)

            bodies: list[str] = []
            for policy_name in variant.policies:
                try:
                    policy = ctx.prompt_registry.get(
                        f"policies/{policy_name}",
                        variant="default",
                    )
                except Exception:
                    logger.warning("policies_snippet_missing", policy=policy_name)
                    continue

                if policy.requires_tools and enabled_tool_names is not None:
                    if not any(t in enabled_tool_names for t in policy.requires_tools):
                        logger.debug(
                            "policy_skipped_missing_tools",
                            policy=policy_name,
                            requires=policy.requires_tools,
                        )
                        continue

                body = _substitute(policy.body, variables).strip()
                if body:
                    bodies.append(body)

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
                metadata={"count": len(bodies)},
            )
        except Exception:
            logger.exception("policies_resolve_failed")
            return None


SOURCE_REGISTRY[PoliciesSource.id] = PoliciesSource
