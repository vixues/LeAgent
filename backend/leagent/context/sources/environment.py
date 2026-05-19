"""Environment context source — cwd, git state, OS, date."""

from __future__ import annotations

import asyncio
import os
import platform
from datetime import datetime, timezone

import structlog

from leagent.context.sources import SOURCE_REGISTRY
from leagent.context.sources.base import ContextSource, ResolveContext
from leagent.context.types import (
    ContextBlock,
    ContextScope,
    EnvironmentSnapshot,
    RenderTarget,
)

logger = structlog.get_logger(__name__)


async def _run_git(args: list[str], cwd: str) -> str:
    """Run a git command and return stripped stdout, or empty string on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0:
            return stdout.decode().strip()
    except Exception:
        pass
    return ""


class EnvironmentSource:
    """Collects runtime environment info: date, cwd, OS, git status."""

    id: str = "environment"
    kind: str = "identity"
    scope: ContextScope = ContextScope.TURN
    priority: int = 800
    weight: float = 0.9
    render_target: RenderTarget = RenderTarget.SYSTEM

    def invalidation_key(self, ctx: ResolveContext) -> str:
        return f"environment:{ctx.cwd}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            cwd = ctx.cwd or "."
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            env_val = os.environ.get("ENVIRONMENT", "")
            os_name = platform.system()
            shell = os.environ.get("SHELL", "")

            is_git = (await _run_git(["rev-parse", "--is-inside-work-tree"], cwd)) == "true"
            git_branch = ""
            git_dirty = False
            git_modified_count = 0
            git_ahead = 0
            git_behind = 0

            if is_git:
                git_branch = await _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)

                porcelain = await _run_git(["status", "--porcelain"], cwd)
                if porcelain:
                    git_dirty = True
                    git_modified_count = len(porcelain.splitlines())

                ahead_str = await _run_git(["rev-list", "--count", "HEAD..@{u}"], cwd)
                git_behind = int(ahead_str) if ahead_str.isdigit() else 0

                behind_str = await _run_git(["rev-list", "--count", "@{u}..HEAD"], cwd)
                git_ahead = int(behind_str) if behind_str.isdigit() else 0

            sandbox_mode = ""
            approval_policy = ""
            if ctx.permission_context is not None:
                sandbox_mode = getattr(ctx.permission_context, "mode", "")
                approval_policy = (
                    "bypass" if getattr(ctx.permission_context, "bypass_permissions", False) else "prompt"
                )

            snapshot = EnvironmentSnapshot(
                date=date_str,
                cwd=cwd,
                env=env_val,
                os_name=os_name,
                shell=shell,
                is_git_repo=is_git,
                git_branch=git_branch,
                git_dirty=git_dirty,
                git_modified_count=git_modified_count,
                git_ahead=git_ahead,
                git_behind=git_behind,
                sandbox_mode=sandbox_mode,
                approval_policy=approval_policy,
            )

            kv: dict[str, str] = {
                "date": snapshot.date,
                "cwd": snapshot.cwd,
                "os": snapshot.os_name,
            }
            if snapshot.shell:
                kv["shell"] = snapshot.shell
            if snapshot.env:
                kv["env"] = snapshot.env
            if snapshot.is_git_repo:
                kv["git_repo"] = "true"
                if snapshot.git_branch:
                    kv["git_branch"] = snapshot.git_branch
                if snapshot.git_dirty:
                    kv["git_modified_count"] = str(snapshot.git_modified_count)
                if snapshot.git_ahead:
                    kv["git_ahead"] = str(snapshot.git_ahead)
                if snapshot.git_behind:
                    kv["git_behind"] = str(snapshot.git_behind)
            if snapshot.sandbox_mode:
                kv["sandbox_mode"] = snapshot.sandbox_mode
            if snapshot.approval_policy:
                kv["approval_policy"] = snapshot.approval_policy

            lines = [f"<{k}>{v}</{k}>" for k, v in kv.items() if v]
            if not lines:
                return None

            body = "<environment>\n" + "\n".join(lines) + "\n</environment>"
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
                metadata={"snapshot": snapshot},
            )
        except Exception:
            logger.exception("environment_resolve_failed")
            return None


SOURCE_REGISTRY[EnvironmentSource.id] = EnvironmentSource
