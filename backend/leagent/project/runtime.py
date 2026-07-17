"""Asynchronous dev-server supervisor.

A :class:`DevServerSupervisor` owns at most one running child per
:class:`CodingProject`. It:

1. Resolves and allow-list-checks the argv via
   :func:`binaries.assert_argv_allowed`.
2. Spawns the child with ``asyncio.create_subprocess_exec``,
   capturing stdout and stderr.
3. Streams every line into a bounded ring buffer plus a fan-out of
   ``asyncio.Queue`` consumers (used by the SSE log endpoint and the
   ``ready_regex`` waiter).
4. Returns control once the ready-regex matches, the health probe
   succeeds, or the startup deadline elapses.
5. Cleans up cleanly on stop: graceful terminate, wait, then SIGKILL
   the whole process group (POSIX) or ``taskkill /T /F`` (Windows)
   so detached node sub-processes don't survive the parent.
"""

from __future__ import annotations

import asyncio
import os
import re
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Mapping
from uuid import UUID

import structlog

from leagent.project.binaries import assert_argv_allowed

logger = structlog.get_logger(__name__)


_IS_WINDOWS = sys.platform.startswith("win")


class StartTimeoutError(TimeoutError):
    """Raised when a dev server fails to become ready within the deadline."""


class ServerNotRunningError(LookupError):
    """Raised when an operation targets a project without a live child."""


@dataclass
class LogLine:
    """Single line of captured child output, tagged with sequence + stream."""

    seq: int
    ts: float
    stream: str  # "stdout" or "stderr"
    text: str

    def to_dict(self) -> dict[str, object]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "stream": self.stream,
            "text": self.text,
        }


@dataclass
class RunningServer:
    """Live state of a running child the supervisor owns."""

    project_id: UUID
    pid: int
    port: int
    host: str
    run_seq: int
    started_at: float
    cwd: Path
    argv: tuple[str, ...]
    # URL prefix the child mounted itself under (e.g. Vite --base).
    # Empty means the child serves from "/" and the proxy strips the
    # preview prefix before forwarding.
    path_prefix: str = ""
    last_activity: float = field(default_factory=time.time)
    ready: bool = False


@dataclass
class _ServerSlot:
    """Bookkeeping the supervisor keeps for each running child."""

    server: RunningServer
    process: asyncio.subprocess.Process
    log_buffer: deque[LogLine]
    log_listeners: list[asyncio.Queue[LogLine | None]]
    stdout_task: asyncio.Task[None]
    stderr_task: asyncio.Task[None]
    wait_task: asyncio.Task[int]
    _next_seq: int = 0

    def append_log(self, line: LogLine) -> None:
        self.log_buffer.append(line)
        self.server.last_activity = line.ts
        for queue in self.log_listeners:
            try:
                queue.put_nowait(line)
            except asyncio.QueueFull:
                pass


class DevServerSupervisor:
    """Spawns, watches, log-streams, and stops dev-server children.

    The supervisor is process-wide; the singleton lives on
    :class:`CodingProjectManager`. All public methods are coroutines
    so they cooperate with the FastAPI event loop.
    """

    def __init__(
        self,
        *,
        log_buffer_lines: int = 4000,
        startup_timeout_sec: float = 120.0,
    ) -> None:
        self._log_buffer_lines = max(64, int(log_buffer_lines))
        self._default_startup_timeout = float(startup_timeout_sec)
        self._slots: dict[UUID, _ServerSlot] = {}
        self._lock = asyncio.Lock()
        self._run_seq: dict[UUID, int] = {}

    # -- query --------------------------------------------------------

    def is_running(self, project_id: UUID) -> bool:
        slot = self._slots.get(project_id)
        if slot is None:
            return False
        return slot.process.returncode is None

    def get(self, project_id: UUID) -> RunningServer | None:
        slot = self._slots.get(project_id)
        return None if slot is None else slot.server

    def list_running(self) -> list[RunningServer]:
        return [
            slot.server
            for slot in self._slots.values()
            if slot.process.returncode is None
        ]

    # -- log access ---------------------------------------------------

    def snapshot_logs(self, project_id: UUID, *, max_lines: int = 200) -> list[LogLine]:
        slot = self._slots.get(project_id)
        if slot is None:
            return []
        if max_lines <= 0:
            return list(slot.log_buffer)
        return list(slot.log_buffer)[-max_lines:]

    async def stream_logs(
        self, project_id: UUID
    ) -> AsyncIterator[LogLine | None]:
        """Yield buffered + live lines until the child exits.

        A trailing ``None`` is yielded when the child terminates so
        SSE consumers can close the connection cleanly.
        """
        slot = self._slots.get(project_id)
        if slot is None:
            raise ServerNotRunningError(str(project_id))

        for line in list(slot.log_buffer):
            yield line

        queue: asyncio.Queue[LogLine | None] = asyncio.Queue(maxsize=512)
        slot.log_listeners.append(queue)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
            yield None
        finally:
            try:
                slot.log_listeners.remove(queue)
            except ValueError:
                pass

    # -- start --------------------------------------------------------

    async def start(
        self,
        *,
        project_id: UUID,
        cwd: Path,
        argv: tuple[str, ...],
        host: str,
        port: int,
        ready_regex: str | None = None,
        env: Mapping[str, str] | None = None,
        startup_timeout_sec: float | None = None,
        path_prefix: str = "",
    ) -> RunningServer:
        """Spawn the child and wait for it to become ready."""
        async with self._lock:
            if self.is_running(project_id):
                raise RuntimeError(
                    f"Dev server for {project_id} is already running"
                )
            await self._cleanup_stale_slot(project_id)

            checked_argv = assert_argv_allowed(argv)

            full_env = dict(os.environ)
            if env:
                full_env.update({str(k): str(v) for k, v in env.items()})

            kwargs: dict[str, object] = {
                "cwd": str(cwd),
                "env": full_env,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "stdin": subprocess.DEVNULL,
            }

            if _IS_WINDOWS:
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True

            logger.info(
                "coding_projects_supervisor_spawn",
                project_id=str(project_id),
                argv=list(checked_argv),
                cwd=str(cwd),
                port=port,
                host=host,
            )

            try:
                process = await asyncio.create_subprocess_exec(
                    *checked_argv, **kwargs
                )
            except FileNotFoundError as exc:
                raise FileNotFoundError(
                    f"Executable not found: {checked_argv[0]}"
                ) from exc

            run_seq = self._run_seq.get(project_id, 0) + 1
            self._run_seq[project_id] = run_seq

            server = RunningServer(
                project_id=project_id,
                pid=process.pid,
                port=port,
                host=host,
                run_seq=run_seq,
                started_at=time.time(),
                cwd=cwd,
                argv=checked_argv,
                path_prefix=path_prefix,
            )

            ready_event = asyncio.Event()
            slot = _ServerSlot(
                server=server,
                process=process,
                log_buffer=deque(maxlen=self._log_buffer_lines),
                log_listeners=[],
                stdout_task=asyncio.create_task(
                    self._pump_stream(
                        project_id,
                        process.stdout,
                        "stdout",
                        ready_regex,
                        ready_event,
                    ),
                    name=f"coding-projects-stdout:{project_id}",
                ),
                stderr_task=asyncio.create_task(
                    self._pump_stream(
                        project_id,
                        process.stderr,
                        "stderr",
                        ready_regex,
                        ready_event,
                    ),
                    name=f"coding-projects-stderr:{project_id}",
                ),
                wait_task=asyncio.create_task(
                    process.wait(),
                    name=f"coding-projects-wait:{project_id}",
                ),
            )
            self._slots[project_id] = slot

        deadline = startup_timeout_sec or self._default_startup_timeout
        if not ready_regex:
            await asyncio.sleep(0)
            slot.server.ready = True
            return slot.server

        try:
            await asyncio.wait_for(ready_event.wait(), timeout=deadline)
            slot.server.ready = True
            return slot.server
        except asyncio.TimeoutError as exc:
            await self.stop(project_id)
            raise StartTimeoutError(
                f"Dev server did not match ready_regex within {deadline:.0f}s"
            ) from exc

    async def _pump_stream(
        self,
        project_id: UUID,
        stream: asyncio.StreamReader | None,
        kind: str,
        ready_regex: str | None,
        ready_event: asyncio.Event,
    ) -> None:
        if stream is None:
            return
        slot = self._slots.get(project_id)
        if slot is None:
            return
        pattern = re.compile(ready_regex) if ready_regex else None
        try:
            while True:
                raw = await stream.readline()
                if not raw:
                    break
                text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                slot._next_seq += 1
                line = LogLine(
                    seq=slot._next_seq,
                    ts=time.time(),
                    stream=kind,
                    text=text,
                )
                slot.append_log(line)
                if pattern is not None and not ready_event.is_set():
                    if pattern.search(text):
                        ready_event.set()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "coding_projects_supervisor_pump_error",
                project_id=str(project_id),
                kind=kind,
                error=str(exc),
            )
        finally:
            # Wake listeners so they don't dangle when the child exits.
            for queue in slot.log_listeners:
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass

    # -- stop ---------------------------------------------------------

    async def stop(
        self,
        project_id: UUID,
        *,
        graceful_timeout: float = 5.0,
    ) -> None:
        slot = self._slots.get(project_id)
        if slot is None:
            return
        process = slot.process
        if process.returncode is not None:
            await self._cleanup_stale_slot(project_id)
            return

        logger.info(
            "coding_projects_supervisor_stop",
            project_id=str(project_id),
            pid=process.pid,
        )

        await self._terminate_process_tree(process)

        try:
            await asyncio.wait_for(process.wait(), timeout=graceful_timeout)
        except asyncio.TimeoutError:
            await self._kill_process_tree(process)
            try:
                await asyncio.wait_for(process.wait(), timeout=graceful_timeout)
            except asyncio.TimeoutError:
                logger.error(
                    "coding_projects_supervisor_kill_failed",
                    project_id=str(project_id),
                    pid=process.pid,
                )

        await self._cleanup_stale_slot(project_id)

    async def _terminate_process_tree(self, proc: asyncio.subprocess.Process) -> None:
        try:
            if _IS_WINDOWS:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                try:
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    proc.terminate()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "coding_projects_supervisor_terminate_error",
                pid=proc.pid,
                error=str(exc),
            )

    async def _kill_process_tree(self, proc: asyncio.subprocess.Process) -> None:
        try:
            if _IS_WINDOWS:
                # Force-kill the whole tree; pid is ignored on the
                # /T /F path because we pass /PID explicitly.
                taskkill = await asyncio.create_subprocess_exec(
                    "taskkill",
                    "/PID",
                    str(proc.pid),
                    "/T",
                    "/F",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                try:
                    await asyncio.wait_for(taskkill.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
            else:
                try:
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "coding_projects_supervisor_kill_error",
                pid=proc.pid,
                error=str(exc),
            )

    async def _cleanup_stale_slot(self, project_id: UUID) -> None:
        slot = self._slots.pop(project_id, None)
        if slot is None:
            return
        for task in (slot.stdout_task, slot.stderr_task, slot.wait_task):
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
        for queue in slot.log_listeners:
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    # -- bulk shutdown ------------------------------------------------

    async def shutdown_all(self) -> None:
        for project_id in list(self._slots):
            try:
                await self.stop(project_id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "coding_projects_supervisor_shutdown_error",
                    project_id=str(project_id),
                    exc_info=True,
                )
