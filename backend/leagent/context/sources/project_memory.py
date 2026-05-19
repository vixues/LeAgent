"""Project memory context source — discovers and injects AGENTS.md / memory.md files."""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import os
from pathlib import Path

import structlog

from leagent.context.sources import SOURCE_REGISTRY
from leagent.context.sources.base import ContextSource, ResolveContext
from leagent.context.types import (
    ContextBlock,
    ContextScope,
    ProjectMemoryOrigin,
    ProjectMemorySource as ProjectMemoryRecord,
    RenderTarget,
)

logger = structlog.get_logger(__name__)

_MAX_CONTENT_CHARS = 4000
_TRUNCATION_MARKER = "\n...[truncated]"


def _leagent_home() -> Path:
    return Path(os.environ.get("LEAGENT_HOME", Path.home() / ".leagent"))


async def _git_toplevel(cwd: str) -> str | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--show-toplevel",
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0:
            return stdout.decode().strip()
    except Exception:
        pass
    return None


def _matches_list(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(os.path.basename(path), pattern):
            return True
    return False


def _read_truncated(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if len(content) > _MAX_CONTENT_CHARS:
        return content[:_MAX_CONTENT_CHARS] + _TRUNCATION_MARKER
    return content


class ProjectMemorySource:
    """Three-bucket discovery of AGENTS.md and memory.md files."""

    id: str = "project_memory"
    kind: str = "identity"
    scope: ContextScope = ContextScope.SESSION
    priority: int = 700
    weight: float = 0.8
    render_target: RenderTarget = RenderTarget.SYSTEM

    def invalidation_key(self, ctx: ResolveContext) -> str:
        denylist_hash = hashlib.md5(
            "|".join(sorted(ctx.project_memory_denylist)).encode()
        ).hexdigest()[:8]
        return f"project_memory:{ctx.cwd}:{denylist_hash}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            cwd = Path(ctx.cwd).resolve()
            denylist = ctx.project_memory_denylist
            allowlist = ctx.project_memory_allowlist

            candidates: list[tuple[Path, ProjectMemoryOrigin]] = []

            # --- Global bucket ---
            global_agents = _leagent_home() / "AGENTS.md"
            if global_agents.is_file():
                candidates.append((global_agents, ProjectMemoryOrigin.GLOBAL))

            # --- Project bucket: walk from cwd up to repo root (or fs root) ---
            repo_root: Path | None = None
            toplevel = await _git_toplevel(str(cwd))
            if toplevel:
                repo_root = Path(toplevel).resolve()

            stop_at = repo_root if (repo_root and ctx.respect_git_boundary) else Path(cwd.anchor)
            current = cwd
            project_paths_seen: set[Path] = set()

            while True:
                for name in ("AGENTS.md", ".leagent/memory.md"):
                    candidate = current / name
                    if candidate.is_file() and candidate not in project_paths_seen:
                        project_paths_seen.add(candidate)
                        candidates.append((candidate, ProjectMemoryOrigin.PROJECT))
                if current == stop_at or current == current.parent:
                    break
                current = current.parent

            # --- Local bucket: cwd/AGENTS.md only if cwd is strictly deeper than project root ---
            effective_root = repo_root or stop_at
            if cwd != effective_root:
                local_agents = cwd / "AGENTS.md"
                if local_agents.is_file() and local_agents not in project_paths_seen:
                    candidates.append((local_agents, ProjectMemoryOrigin.LOCAL))

            # --- Filter and read ---
            sources: list[ProjectMemoryRecord] = []
            passing_sections: list[str] = []

            for path, origin in candidates:
                path_str = str(path)

                if _matches_list(path_str, allowlist):
                    pass  # allowlist bypasses deny
                elif _matches_list(path_str, denylist):
                    sources.append(
                        ProjectMemoryRecord(
                            path=path_str,
                            origin=origin,
                            content="",
                            size=0,
                            injected=False,
                            skip_reason="denylisted",
                        )
                    )
                    continue

                content = _read_truncated(path)
                if not content.strip():
                    continue

                sources.append(
                    ProjectMemoryRecord(
                        path=path_str,
                        origin=origin,
                        content=content,
                        size=len(content),
                        injected=True,
                    )
                )
                fname = path.name
                passing_sections.append(f"<{fname}>\n{content}\n</{fname}>")

            if not passing_sections:
                return None

            body = "<project_memory>\n" + "\n\n".join(passing_sections) + "\n</project_memory>"
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
                    "sources": sources,
                    "cache_boundary": True,
                },
            )
        except Exception:
            logger.exception("project_memory_resolve_failed")
            return None


SOURCE_REGISTRY[ProjectMemorySource.id] = ProjectMemorySource
