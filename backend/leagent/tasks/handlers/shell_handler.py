"""``TaskHandler`` that executes a shell command without a shell.

Uses :func:`asyncio.create_subprocess_exec` (``shell=False``) so that
input list items are never interpreted by /bin/sh. Callers pass either
``cmd: [str, ...]`` (preferred) or ``argv: [str, ...]``. A bare
``command: str`` value is rejected unless ``allow_shell`` is true in
settings — kept behind a flag to avoid shell-injection regressions.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
from typing import TYPE_CHECKING, Any

from leagent.services.database.models.task import TaskContext, TaskType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ShellTaskHandler:
    """Run a subprocess and stream stdout/stderr into the task log."""

    name = "shell_task_handler"
    task_type: TaskType = TaskType.SHELL

    def __init__(self, *, allow_shell_default: bool = False) -> None:
        self._allow_shell_default = allow_shell_default

    async def spawn(
        self,
        task_ctx: TaskContext,
        params: dict[str, Any],
        session: "AsyncSession",
    ) -> dict[str, Any]:
        argv = _extract_argv(params)
        if not argv:
            raise ValueError(
                "Shell task requires 'cmd' or 'argv' as a list of strings"
            )

        cwd = params.get("cwd")
        env_extra = params.get("env") or {}
        timeout_sec = params.get("timeout_sec")

        env = {**os.environ, **{str(k): str(v) for k, v in env_extra.items()}}

        task_ctx.append_output(f"$ {' '.join(shlex.quote(a) for a in argv)}\n")

        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async def _stream() -> None:
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                try:
                    task_ctx.append_output(line.decode("utf-8", errors="replace"))
                except Exception:
                    logger.debug("shell output append failed", exc_info=True)

        stream_task = asyncio.create_task(_stream())
        abort_task = asyncio.create_task(task_ctx.abort_event.wait())

        try:
            done, _ = await asyncio.wait(
                {stream_task, abort_task},
                timeout=timeout_sec,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if abort_task in done and stream_task not in done:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
        finally:
            for t in (stream_task, abort_task):
                if not t.done():
                    t.cancel()

        rc = await proc.wait()
        task_ctx.append_output(f"\n[exit {rc}]\n")
        if rc != 0:
            raise RuntimeError(f"Shell command exited with code {rc}")
        return {"exit_code": rc, "argv": argv}

    async def kill(self, task_id: str, session: "AsyncSession") -> None:
        return None


def _extract_argv(params: dict[str, Any]) -> list[str]:
    for key in ("cmd", "argv", "args"):
        v = params.get(key)
        if isinstance(v, list) and all(isinstance(x, (str, int, float)) for x in v):
            return [str(x) for x in v]
    return []
