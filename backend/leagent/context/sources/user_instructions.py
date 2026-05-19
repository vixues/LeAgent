"""User instructions context source — global instructions.md file."""

from __future__ import annotations

import os
from pathlib import Path

import structlog

from leagent.context.sources import SOURCE_REGISTRY
from leagent.context.sources.base import ContextSource, ResolveContext
from leagent.context.types import ContextBlock, ContextScope, RenderTarget

logger = structlog.get_logger(__name__)

_MAX_CHARS = 2000


def _leagent_home() -> Path:
    return Path(os.environ.get("LEAGENT_HOME", Path.home() / ".leagent"))


class UserInstructionsSource:
    """Loads the user's global instructions.md file."""

    id: str = "user_instructions"
    kind: str = "identity"
    scope: ContextScope = ContextScope.SESSION
    priority: int = 600
    weight: float = 0.7
    render_target: RenderTarget = RenderTarget.SYSTEM

    def invalidation_key(self, ctx: ResolveContext) -> str:
        return f"user_instructions:{_leagent_home()}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            instructions_path = _leagent_home() / "instructions.md"
            if not instructions_path.is_file():
                return None

            try:
                content = instructions_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                logger.warning("user_instructions_read_failed", path=str(instructions_path))
                return None

            if not content.strip():
                return None

            if len(content) > _MAX_CHARS:
                content = content[:_MAX_CHARS] + "\n...[truncated]"

            body = f"<user_instructions>\n{content}\n</user_instructions>"
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
            )
        except Exception:
            logger.exception("user_instructions_resolve_failed")
            return None


SOURCE_REGISTRY[UserInstructionsSource.id] = UserInstructionsSource
