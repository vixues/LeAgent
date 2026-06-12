"""Workflow worker process.

Long-lived entry point that reuses a single :class:`WorkflowExecutor`
instance across queued jobs. Responsibilities:

- Bootstrap the node registry (built-ins + entrypoints + custom dirs).
- Subscribe to a :class:`PromptQueue`.
- Drive :meth:`WorkflowExecutor.execute_async` per job (HTTP/cron use
  :meth:`WorkflowService.start` as the unified entry; the worker consumes
  the queue directly).
- Publish lifecycle events to the shared :class:`ExecutionEventBus` and
  :class:`EventManager` (via ``ServiceManager`` wiring).
- Graceful drain on SIGTERM / SIGINT.

The worker is deliberately transport-agnostic: it uses only the
``PromptQueue`` + ``ExecutionEventBus`` protocols so tests can swap in
the in-memory variants without touching Redis.
"""

from __future__ import annotations

import asyncio
import signal
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import structlog

from .engine.executor import WorkflowExecutor
from .engine.progress import ProgressEvent
from .io import WorkflowDocument, load
from .nodes import bootstrap as bootstrap_nodes
from .queue.base import PromptHistoryEntry, PromptItem, PromptQueue

logger = structlog.get_logger(__name__)


FlowLoader = Callable[[str], Awaitable[WorkflowDocument | None]]
ExecutionPublisher = Callable[[str, ProgressEvent], Awaitable[None]]
ExecutionStateUpdater = Callable[..., Awaitable[None]]


@dataclass
class WorkerOptions:
    concurrency: int = 1
    idle_sleep_sec: float = 0.1
    drain_timeout_sec: float = 30.0
    custom_nodes_dir: str | None = None
    # When Redis (or queue) errors repeat, cap backoff and avoid logging a full traceback every poll.
    queue_error_backoff_max_sec: float = 30.0
    queue_get_traceback_interval: int = 25


class WorkflowWorker:
    def __init__(
        self,
        queue: PromptQueue,
        executor: WorkflowExecutor,
        *,
        flow_loader: FlowLoader,
        publish: ExecutionPublisher | None = None,
        update_execution_state: ExecutionStateUpdater | None = None,
        options: WorkerOptions | None = None,
    ) -> None:
        self._queue = queue
        self._executor = executor
        self._flow_loader = flow_loader
        self._publish = publish
        self._update_execution_state = update_execution_state
        self._options = options or WorkerOptions()
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        summary = await bootstrap_nodes(custom_dirs=[self._options.custom_nodes_dir]
                                        if self._options.custom_nodes_dir else None)
        logger.info("workflow_worker_ready",
                    node_count=sum(len(v) for v in summary.values()),
                    summary=summary)
        self._install_signal_handlers()
        if self._publish is not None:
            self._executor.register_progress_handler(self._handle_progress)
        for i in range(self._options.concurrency):
            self._tasks.append(asyncio.create_task(self._run_loop(worker_id=i),
                                                     name=f"workflow-worker-{i}"))
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self) -> None:
        self._stop.set()
        deadline = time.monotonic() + self._options.drain_timeout_sec
        for task in self._tasks:
            if task.done():
                continue
            remaining = max(0.0, deadline - time.monotonic())
            try:
                await asyncio.wait_for(task, timeout=remaining)
            except asyncio.TimeoutError:
                task.cancel()

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:  # Windows
                break

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run_loop(self, worker_id: int) -> None:
        log = logger.bind(worker_id=worker_id)
        consecutive_queue_failures = 0
        while not self._stop.is_set():
            try:
                item = await self._queue.get(timeout=1.0)
                consecutive_queue_failures = 0
            except Exception as exc:
                consecutive_queue_failures += 1
                err_msg = str(exc)
                if len(err_msg) > 500:
                    err_msg = err_msg[:500] + "…"
                log_kwargs: dict[str, Any] = {
                    "error_type": type(exc).__name__,
                    "error": err_msg,
                    "consecutive_failures": consecutive_queue_failures,
                }
                n = self._options.queue_get_traceback_interval
                if consecutive_queue_failures == 1 or (
                    n > 0 and consecutive_queue_failures % n == 0
                ):
                    log.error("queue_get_failed", exc_info=True, **log_kwargs)
                else:
                    log.error("queue_get_failed", **log_kwargs)
                exp = min(max(0, consecutive_queue_failures - 1), 12)
                backoff = min(
                    self._options.idle_sleep_sec * (2**exp),
                    self._options.queue_error_backoff_max_sec,
                )
                await asyncio.sleep(backoff)
                continue
            if item is None:
                continue
            await self._process_item(item, log)

    async def _process_item(self, item: PromptItem, log: Any) -> None:
        start = time.monotonic()
        status = "failed"
        outputs: dict[str, Any] = {}
        error: str | None = None
        metadata: dict[str, Any] = {}
        try:
            if self._update_execution_state is not None:
                try:
                    await self._update_execution_state(
                        prompt_id=item.prompt_id,
                        status="running",
                    )
                except Exception:
                    log.warning("workflow_execution_state_update_failed", prompt_id=item.prompt_id)
            doc = await self._flow_loader(item.flow_id)
            if doc is None:
                raise LookupError(f"Flow {item.flow_id} not found")
            result = await self._executor.execute_async(
                doc,
                item.inputs,
                prompt_id=item.prompt_id,
                extra_data={"user_id": item.user_id, **item.extra_data},
            )
            status = result.status.value
            outputs = dict(result.outputs or {})
            metadata = dict(result.metadata or {})
            if result.errors:
                error = "; ".join(result.errors)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            log.error("workflow_execution_failed", prompt_id=item.prompt_id, error=error, exc_info=True)
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            if self._update_execution_state is not None:
                try:
                    await self._update_execution_state(
                        prompt_id=item.prompt_id,
                        status=status,
                        outputs=outputs,
                        error=error,
                        duration_ms=duration_ms,
                        metadata=metadata,
                    )
                except Exception:
                    log.warning("workflow_execution_state_finalize_failed", prompt_id=item.prompt_id)
            await self._queue.task_done(item, PromptHistoryEntry(
                prompt_id=item.prompt_id,
                status=status,
                outputs=outputs,
                error=error,
                duration_ms=duration_ms,
                metadata=metadata,
            ))

    async def _handle_progress(self, event: ProgressEvent) -> None:
        if self._publish is None:
            return
        try:
            await self._publish(event.prompt_id, event)
        except Exception:
            logger.error("publish_event_failed", exc_info=True)


# ---------------------------------------------------------------------------
# Default flow loader (reads Flow.data from the database)
# ---------------------------------------------------------------------------


def make_db_flow_loader(db_service: Any) -> FlowLoader:
    async def _loader(flow_id: str) -> WorkflowDocument | None:
        import json
        from sqlmodel import select
        from leagent.db.models.flow import Flow
        try:
            from uuid import UUID
            flow_uuid = UUID(flow_id)
        except ValueError:
            flow_uuid = None
        async with db_service.session() as session:
            if flow_uuid is not None:
                flow = await session.get(Flow, flow_uuid)
            else:
                result = await session.exec(select(Flow).where(Flow.name == flow_id,
                                                               Flow.is_deleted == False))
                flow = result.first()
            if not flow or not flow.data:
                return None
            try:
                raw = json.loads(flow.data)
                return load(raw)
            except Exception:  # noqa: BLE001
                return None

    return _loader
