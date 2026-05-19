"""Job queue service for task management and worker coordination."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from heapq import heappop, heappush
from typing import TYPE_CHECKING, Any, Callable, Coroutine
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from leagent.services.base import Service, ServiceType, service_factory

if TYPE_CHECKING:
    from leagent.config.settings import Settings

logger = logging.getLogger(__name__)

JobHandler = Callable[["Job"], Coroutine[Any, Any, Any]]


class JobStatus(str, Enum):
    """Job execution status."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"
    TIMEOUT = "timeout"


class JobPriority(int, Enum):
    """Job priority levels (lower = higher priority)."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass(order=True)
class PriorityJob:
    """Job wrapper for priority queue ordering."""

    priority: int
    timestamp: float
    job: Any = field(compare=False)


class Job(BaseModel):
    """Job representation for the queue."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: JobPriority = JobPriority.NORMAL
    status: JobStatus = JobStatus.PENDING
    queue: str = "default"

    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    max_retries: int = 3
    retry_count: int = 0
    retry_delay_seconds: int = 60

    timeout_seconds: int = 300
    progress: float = 0.0
    result: Any = None
    error: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)
    worker_id: str | None = None


class JobResult(BaseModel):
    """Result of a job execution."""

    job_id: UUID
    status: JobStatus
    result: Any = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None


class InMemoryQueue:
    """In-memory priority queue."""

    def __init__(self) -> None:
        self._queues: dict[str, list[PriorityJob]] = {}
        self._jobs: dict[UUID, Job] = {}
        self._lock = asyncio.Lock()

    async def enqueue(self, job: Job) -> None:
        """Add a job to the queue."""
        async with self._lock:
            if job.queue not in self._queues:
                self._queues[job.queue] = []

            priority_job = PriorityJob(
                priority=job.priority.value,
                timestamp=time.time(),
                job=job,
            )
            heappush(self._queues[job.queue], priority_job)
            self._jobs[job.id] = job

    async def dequeue(self, queue: str = "default") -> Job | None:
        """Get the next job from the queue."""
        async with self._lock:
            if queue not in self._queues or not self._queues[queue]:
                return None

            priority_job = heappop(self._queues[queue])
            return priority_job.job

    async def get(self, job_id: UUID) -> Job | None:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    async def update(self, job: Job) -> None:
        """Update a job's state."""
        async with self._lock:
            self._jobs[job.id] = job

    async def delete(self, job_id: UUID) -> bool:
        """Remove a job."""
        async with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    async def list_pending(self, queue: str = "default") -> list[Job]:
        """List pending jobs in a queue."""
        if queue not in self._queues:
            return []
        return [pj.job for pj in self._queues[queue]]

    async def size(self, queue: str = "default") -> int:
        """Get queue size."""
        if queue not in self._queues:
            return 0
        return len(self._queues[queue])


@service_factory(ServiceType.JOB_QUEUE)
class JobQueueService(Service):
    """Job queue service for task management.

    Features:
    - Priority-based job queuing
    - Job status tracking
    - Retry logic with exponential backoff
    - Worker coordination
    - Job timeout handling
    """

    def __init__(
        self,
        settings: "Settings",
        cache_service: Any = None,
    ) -> None:
        super().__init__(settings)
        self._memory_queue = InMemoryQueue()
        self._handlers: dict[str, JobHandler] = {}
        self._workers: dict[str, asyncio.Task] = {}
        self._worker_id = f"worker-{uuid4().hex[:8]}"
        self._shutdown_event = asyncio.Event()

    @property
    def name(self) -> str:
        return "JobQueueService"

    async def _do_start(self) -> None:
        pass

    async def _do_stop(self) -> None:
        """Stop workers and close connections."""
        self._shutdown_event.set()

        for name, task in self._workers.items():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                logger.warning("Worker %s did not shut down cleanly", name)

        self._workers.clear()

    async def _do_health_check(self) -> dict[str, Any]:
        """Return queue health status."""
        return {
            "backend": "memory",
            "worker_id": self._worker_id,
            "active_workers": len(self._workers),
            "registered_handlers": list(self._handlers.keys()),
        }

    def register_handler(self, job_name: str, handler: JobHandler) -> None:
        """Register a handler for a job type.

        Args:
            job_name: The job name to handle
            handler: Async function to execute the job
        """
        self._handlers[job_name] = handler
        logger.debug("Registered handler for job type: %s", job_name)

    async def enqueue(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
        *,
        priority: JobPriority = JobPriority.NORMAL,
        queue: str = "default",
        delay_seconds: int = 0,
        max_retries: int = 3,
        timeout_seconds: int = 300,
        metadata: dict[str, Any] | None = None,
    ) -> Job:
        """Add a job to the queue.

        Args:
            name: Job type name
            payload: Job payload data
            priority: Job priority level
            queue: Queue name
            delay_seconds: Delay before job becomes available
            max_retries: Maximum retry attempts
            timeout_seconds: Job timeout
            metadata: Additional metadata

        Returns:
            The created job
        """
        job = Job(
            name=name,
            payload=payload or {},
            priority=priority,
            queue=queue,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            metadata=metadata or {},
            status=JobStatus.QUEUED,
        )

        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        await self._memory_queue.enqueue(job)

        logger.debug("Enqueued job %s (%s) to queue %s", job.id, name, queue)
        return job

    async def get_job(self, job_id: UUID) -> Job | None:
        """Get a job by ID.

        Args:
            job_id: The job ID

        Returns:
            The job or None
        """
        return await self._memory_queue.get(job_id)

    async def update_job(self, job: Job) -> None:
        """Update a job's state.

        Args:
            job: The job to update
        """
        await self._memory_queue.update(job)

    async def cancel_job(self, job_id: UUID) -> bool:
        """Cancel a pending or running job.

        Args:
            job_id: The job ID

        Returns:
            True if cancelled
        """
        job = await self.get_job(job_id)
        if not job:
            return False

        if job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
            return False

        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.utcnow()
        await self.update_job(job)

        logger.info("Cancelled job %s", job_id)
        return True

    async def update_progress(
        self,
        job_id: UUID,
        progress: float,
        *,
        message: str | None = None,
    ) -> None:
        """Update job progress.

        Args:
            job_id: The job ID
            progress: Progress percentage (0-100)
            message: Optional status message
        """
        job = await self.get_job(job_id)
        if job:
            job.progress = min(100.0, max(0.0, progress))
            if message:
                job.metadata["status_message"] = message
            await self.update_job(job)

    async def _dequeue(self, queue: str = "default") -> Job | None:
        """Get the next job from a queue.

        Args:
            queue: Queue name

        Returns:
            The next job or None
        """
        return await self._memory_queue.dequeue(queue)

    async def _execute_job(self, job: Job) -> JobResult:
        """Execute a job with the registered handler.

        Args:
            job: The job to execute

        Returns:
            The job result
        """
        handler = self._handlers.get(job.name)
        if not handler:
            return JobResult(
                job_id=job.id,
                status=JobStatus.FAILED,
                error=f"No handler registered for job type: {job.name}",
            )

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        job.worker_id = self._worker_id
        await self.update_job(job)

        start_time = time.time()

        try:
            result = await asyncio.wait_for(
                handler(job),
                timeout=job.timeout_seconds,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.result = result
            job.progress = 100.0
            await self.update_job(job)

            return JobResult(
                job_id=job.id,
                status=JobStatus.COMPLETED,
                result=result,
                started_at=job.started_at,
                completed_at=job.completed_at,
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            job.status = JobStatus.TIMEOUT
            job.completed_at = datetime.utcnow()
            job.error = f"Job timed out after {job.timeout_seconds}s"
            await self.update_job(job)

            return JobResult(
                job_id=job.id,
                status=JobStatus.TIMEOUT,
                error=job.error,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)

            if job.retry_count < job.max_retries:
                job.status = JobStatus.RETRYING
                job.retry_count += 1
                job.error = error_msg
                await self.update_job(job)

                delay = job.retry_delay_seconds * (2 ** (job.retry_count - 1))
                await self.enqueue(
                    job.name,
                    job.payload,
                    priority=job.priority,
                    queue=job.queue,
                    delay_seconds=delay,
                    max_retries=job.max_retries - job.retry_count,
                    timeout_seconds=job.timeout_seconds,
                    metadata={**job.metadata, "retry_of": str(job.id)},
                )

                logger.warning(
                    "Job %s failed, scheduling retry %d/%d in %ds",
                    job.id,
                    job.retry_count,
                    job.max_retries,
                    delay,
                )
            else:
                job.status = JobStatus.FAILED
                job.completed_at = datetime.utcnow()
                job.error = error_msg
                await self.update_job(job)

            return JobResult(
                job_id=job.id,
                status=job.status,
                error=error_msg,
                started_at=job.started_at,
                completed_at=job.completed_at,
                duration_ms=duration_ms,
            )

    async def start_worker(
        self,
        queue: str = "default",
        *,
        concurrency: int = 1,
    ) -> None:
        """Start a worker processing jobs from a queue.

        Args:
            queue: Queue to process
            concurrency: Number of concurrent jobs
        """
        worker_name = f"{queue}-{uuid4().hex[:6]}"

        async def worker_loop():
            logger.info("Worker %s started for queue %s", worker_name, queue)
            semaphore = asyncio.Semaphore(concurrency)

            while not self._shutdown_event.is_set():
                try:
                    job = await self._dequeue(queue)
                    if job is None:
                        await asyncio.sleep(0.1)
                        continue

                    async with semaphore:
                        await self._execute_job(job)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Worker error: %s", e)
                    await asyncio.sleep(1)

            logger.info("Worker %s stopped", worker_name)

        task = asyncio.create_task(worker_loop())
        self._workers[worker_name] = task

    async def stop_worker(self, worker_name: str) -> None:
        """Stop a specific worker.

        Args:
            worker_name: The worker to stop
        """
        if worker_name in self._workers:
            self._workers[worker_name].cancel()
            del self._workers[worker_name]

    async def get_queue_stats(self, queue: str = "default") -> dict[str, Any]:
        """Get statistics for a queue.

        Args:
            queue: Queue name

        Returns:
            Queue statistics
        """
        return {
            "queue": queue,
            "pending": await self._memory_queue.size(queue),
            "delayed": 0,
        }

    async def list_jobs(
        self,
        *,
        queue: str = "default",
        status: JobStatus | None = None,
        limit: int = 100,
    ) -> list[Job]:
        """List jobs with optional filtering.

        Args:
            queue: Queue name
            status: Filter by status
            limit: Maximum results

        Returns:
            List of jobs
        """
        jobs = await self._memory_queue.list_pending(queue)
        if status:
            jobs = [j for j in jobs if j.status == status]
        return jobs[:limit]

    async def retry_failed_jobs(self, queue: str = "default") -> int:
        """Retry all failed jobs in a queue.

        Args:
            queue: Queue name

        Returns:
            Number of jobs re-queued
        """
        jobs = await self.list_jobs(queue=queue, status=JobStatus.FAILED)
        count = 0

        for job in jobs:
            await self.enqueue(
                job.name,
                job.payload,
                priority=job.priority,
                queue=job.queue,
                metadata={**job.metadata, "retry_of": str(job.id)},
            )
            count += 1

        return count


_job_queue_service: JobQueueService | None = None


def get_job_queue_service() -> JobQueueService:
    """Get the global job queue service instance."""
    if _job_queue_service is None:
        raise RuntimeError("JobQueueService not initialized")
    return _job_queue_service


async def init_job_queue_service(
    settings: "Settings",
    cache_service: Any = None,
) -> JobQueueService:
    global _job_queue_service
    _job_queue_service = JobQueueService(settings)
    await _job_queue_service.start()
    return _job_queue_service
