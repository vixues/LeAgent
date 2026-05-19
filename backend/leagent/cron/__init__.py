"""Scheduled tasks / cron jobs package.

This package provides a complete cron scheduling system for LeAgent,
including job management, execution, persistence, and lifecycle hooks.

Example usage:

    from leagent.cron import (
        CronJob,
        CronManager,
        CronExecutor,
        JsonJobRepository,
    )

    # Create repository and executor
    repository = JsonJobRepository("jobs.json")
    await repository.initialize()

    executor = CronExecutor(workflow_executor=workflow_executor)

    # Create and start manager
    manager = CronManager(
        repository=repository,
        executor=executor,
    )
    await manager.start()

    # Add a job
    job = CronJob(
        name="Daily Report",
        schedule="0 9 * * *",
        workflow_id="generate-report",
    )
    await manager.add_job(job)

    # Stop when done
    await manager.stop()
"""

from .base import (
    CronExecution,
    CronExecutionStatus,
    CronHeartbeat,
    CronJob,
    CronJobStats,
    CronJobStatus,
    CronJobType,
)
from .executor import (
    CronExecutor,
    ExecutionLogger,
    InMemoryExecutionLogger,
)
from .hooks import (
    CronHookManager,
    HookContext,
    HookEvent,
    HookHandler,
    RegisteredHook,
    logging_hook,
    metrics_hook,
    notification_hook,
)
from .manager import CronManager
from .repository import (
    JobRepository,
    JsonJobRepository,
)
from .scheduler import (
    CronExpressionParser,
    CronField,
    CronScheduler,
    ParsedCronExpression,
    RateLimitBucket,
    RateLimiter,
)

__all__ = [
    # Base types
    "CronJob",
    "CronJobStatus",
    "CronJobType",
    "CronExecution",
    "CronExecutionStatus",
    "CronHeartbeat",
    "CronJobStats",
    # Manager
    "CronManager",
    # Executor
    "CronExecutor",
    "ExecutionLogger",
    "InMemoryExecutionLogger",
    # Repository
    "JobRepository",
    "JsonJobRepository",
    # Scheduler
    "CronScheduler",
    "CronExpressionParser",
    "CronField",
    "ParsedCronExpression",
    "RateLimiter",
    "RateLimitBucket",
    # Hooks
    "CronHookManager",
    "HookEvent",
    "HookContext",
    "HookHandler",
    "RegisteredHook",
    "logging_hook",
    "notification_hook",
    "metrics_hook",
]
