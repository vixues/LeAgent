"""Cron lifecycle hooks for job execution events.

This module provides the CronHookManager for registering and invoking
lifecycle hooks at various stages of job execution.
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

from .base import CronExecution, CronJob

if TYPE_CHECKING:
    from leagent.channels.manager import ChannelManager

logger = structlog.get_logger(__name__)


class HookEvent(str, Enum):
    """Types of cron lifecycle events."""

    JOB_START = "job_start"
    JOB_COMPLETE = "job_complete"
    JOB_FAIL = "job_fail"
    JOB_TIMEOUT = "job_timeout"
    JOB_SKIP = "job_skip"
    JOB_RETRY = "job_retry"

    MANAGER_START = "manager_start"
    MANAGER_STOP = "manager_stop"

    JOB_ADDED = "job_added"
    JOB_REMOVED = "job_removed"
    JOB_UPDATED = "job_updated"
    JOB_PAUSED = "job_paused"
    JOB_RESUMED = "job_resumed"


@dataclass
class HookContext:
    """Context passed to hook handlers."""

    event: HookEvent
    timestamp: datetime = field(default_factory=datetime.utcnow)
    job: CronJob | None = None
    execution: CronExecution | None = None
    error: Exception | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


HookHandler = Callable[[HookContext], Awaitable[None]]


@dataclass
class RegisteredHook:
    """A registered hook handler."""

    event: HookEvent
    handler: HookHandler
    name: str
    priority: int = 0
    enabled: bool = True


class CronHookManager:
    """Manager for cron job lifecycle hooks.

    Allows registration of async handlers for various job events
    and coordinates their invocation during job execution.
    """

    def __init__(
        self,
        channel_manager: ChannelManager | None = None,
        default_notification_channels: list[str] | None = None,
    ):
        """Initialize the hook manager.

        Args:
            channel_manager: Optional channel manager for notifications.
            default_notification_channels: Default channels for notifications.
        """
        self.channel_manager = channel_manager
        self.default_notification_channels = default_notification_channels or []

        self._hooks: dict[HookEvent, list[RegisteredHook]] = {
            event: [] for event in HookEvent
        }
        self._global_hooks: list[RegisteredHook] = []
        self._lock = asyncio.Lock()

    def register(
        self,
        event: HookEvent | str,
        handler: HookHandler,
        name: str | None = None,
        priority: int = 0,
    ) -> None:
        """Register a hook handler for an event.

        Args:
            event: The event to handle (or '*' for all events).
            handler: The async handler function.
            name: Optional name for the handler.
            priority: Handler priority (higher runs first).
        """
        hook = RegisteredHook(
            event=HookEvent(event) if event != "*" else HookEvent.JOB_START,
            handler=handler,
            name=name or handler.__name__,
            priority=priority,
        )

        if event == "*":
            self._global_hooks.append(hook)
            self._global_hooks.sort(key=lambda h: -h.priority)
        else:
            event_type = HookEvent(event)
            self._hooks[event_type].append(hook)
            self._hooks[event_type].sort(key=lambda h: -h.priority)

        logger.debug(
            "cron_hook_registered",
            event=str(event),
            handler=hook.name,
            priority=priority,
        )

    def unregister(self, event: HookEvent | str, name: str) -> bool:
        """Unregister a hook handler.

        Args:
            event: The event type (or '*' for global hooks).
            name: Name of the handler to remove.

        Returns:
            True if handler was removed.
        """
        if event == "*":
            original_len = len(self._global_hooks)
            self._global_hooks = [h for h in self._global_hooks if h.name != name]
            return len(self._global_hooks) < original_len

        event_type = HookEvent(event)
        original_len = len(self._hooks[event_type])
        self._hooks[event_type] = [h for h in self._hooks[event_type] if h.name != name]
        return len(self._hooks[event_type]) < original_len

    async def invoke(self, context: HookContext) -> list[Exception]:
        """Invoke all registered hooks for an event.

        Args:
            context: The hook context.

        Returns:
            List of exceptions from failed handlers.
        """
        errors: list[Exception] = []

        all_hooks = [
            *self._global_hooks,
            *self._hooks.get(context.event, []),
        ]

        all_hooks.sort(key=lambda h: -h.priority)

        for hook in all_hooks:
            if not hook.enabled:
                continue

            try:
                await hook.handler(context)

            except Exception as e:
                logger.error(
                    "cron_hook_error",
                    event=context.event.value,
                    handler=hook.name,
                    error=str(e),
                    exc_info=True,
                )
                errors.append(e)

        return errors

    async def on_job_start(
        self,
        job: CronJob,
        execution: CronExecution,
    ) -> None:
        """Handle job start event.

        Args:
            job: The job that started.
            execution: The execution record.
        """
        context = HookContext(
            event=HookEvent.JOB_START,
            job=job,
            execution=execution,
        )
        await self.invoke(context)

    async def on_job_complete(
        self,
        job: CronJob,
        execution: CronExecution,
    ) -> None:
        """Handle job completion event.

        Args:
            job: The completed job.
            execution: The execution record.
        """
        context = HookContext(
            event=HookEvent.JOB_COMPLETE,
            job=job,
            execution=execution,
        )
        await self.invoke(context)

    async def on_job_fail(
        self,
        job: CronJob,
        execution: CronExecution,
        error: Exception,
    ) -> None:
        """Handle job failure event.

        Args:
            job: The failed job.
            execution: The execution record.
            error: The exception that caused the failure.
        """
        context = HookContext(
            event=HookEvent.JOB_FAIL,
            job=job,
            execution=execution,
            error=error,
        )
        await self.invoke(context)

    async def on_job_timeout(
        self,
        job: CronJob,
        execution: CronExecution,
    ) -> None:
        """Handle job timeout event.

        Args:
            job: The timed out job.
            execution: The execution record.
        """
        context = HookContext(
            event=HookEvent.JOB_TIMEOUT,
            job=job,
            execution=execution,
        )
        await self.invoke(context)

    async def on_job_skip(
        self,
        job: CronJob,
        reason: str,
    ) -> None:
        """Handle job skip event.

        Args:
            job: The skipped job.
            reason: Reason for skipping.
        """
        context = HookContext(
            event=HookEvent.JOB_SKIP,
            job=job,
            metadata={"reason": reason},
        )
        await self.invoke(context)

    async def on_job_retry(
        self,
        job: CronJob,
        execution: CronExecution,
        attempt: int,
        error: Exception,
    ) -> None:
        """Handle job retry event.

        Args:
            job: The job being retried.
            execution: The execution record.
            attempt: Current attempt number.
            error: The error from the previous attempt.
        """
        context = HookContext(
            event=HookEvent.JOB_RETRY,
            job=job,
            execution=execution,
            error=error,
            metadata={"attempt": attempt},
        )
        await self.invoke(context)

    def enable_hook(self, event: HookEvent | str, name: str) -> bool:
        """Enable a disabled hook.

        Args:
            event: The event type.
            name: Name of the handler.

        Returns:
            True if handler was found and enabled.
        """
        return self._set_hook_enabled(event, name, True)

    def disable_hook(self, event: HookEvent | str, name: str) -> bool:
        """Disable a hook without removing it.

        Args:
            event: The event type.
            name: Name of the handler.

        Returns:
            True if handler was found and disabled.
        """
        return self._set_hook_enabled(event, name, False)

    def _set_hook_enabled(self, event: HookEvent | str, name: str, enabled: bool) -> bool:
        """Set the enabled state of a hook."""
        if event == "*":
            for hook in self._global_hooks:
                if hook.name == name:
                    hook.enabled = enabled
                    return True
            return False

        event_type = HookEvent(event)
        for hook in self._hooks[event_type]:
            if hook.name == name:
                hook.enabled = enabled
                return True
        return False

    def list_hooks(self, event: HookEvent | str | None = None) -> list[dict[str, Any]]:
        """List registered hooks.

        Args:
            event: Optional event filter.

        Returns:
            List of hook information dictionaries.
        """
        hooks_info = []

        if event is None or event == "*":
            for hook in self._global_hooks:
                hooks_info.append({
                    "event": "*",
                    "name": hook.name,
                    "priority": hook.priority,
                    "enabled": hook.enabled,
                })

        if event is None:
            for evt, hooks in self._hooks.items():
                for hook in hooks:
                    hooks_info.append({
                        "event": evt.value,
                        "name": hook.name,
                        "priority": hook.priority,
                        "enabled": hook.enabled,
                    })
        elif event != "*":
            event_type = HookEvent(event)
            for hook in self._hooks[event_type]:
                hooks_info.append({
                    "event": event_type.value,
                    "name": hook.name,
                    "priority": hook.priority,
                    "enabled": hook.enabled,
                })

        return hooks_info


def notification_hook(
    channel_manager: ChannelManager,
    channels: list[str],
    events: list[HookEvent] | None = None,
) -> HookHandler:
    """Create a notification hook handler.

    Args:
        channel_manager: Channel manager for sending notifications.
        channels: Channels to send notifications to.
        events: Events to notify on (default: all job events).

    Returns:
        Hook handler function.
    """
    target_events = events or [
        HookEvent.JOB_START,
        HookEvent.JOB_COMPLETE,
        HookEvent.JOB_FAIL,
        HookEvent.JOB_TIMEOUT,
    ]

    async def handler(context: HookContext) -> None:
        if context.event not in target_events:
            return

        if not context.job:
            return

        message = _format_notification_message(context)

        try:
            await channel_manager.broadcast(
                message,
                channels=channels,
                meta={
                    "type": "cron_notification",
                    "event": context.event.value,
                    "job_id": str(context.job.id) if context.job else None,
                    "execution_id": str(context.execution.id) if context.execution else None,
                },
            )
        except Exception as e:
            logger.warning(
                "cron_notification_hook_failed",
                error=str(e),
                channels=channels,
            )

    return handler


def _format_notification_message(context: HookContext) -> str:
    """Format notification message for a hook context."""
    job_name = context.job.name if context.job else "Unknown"

    match context.event:
        case HookEvent.JOB_START:
            return f"[Cron] Job '{job_name}' started"

        case HookEvent.JOB_COMPLETE:
            duration = context.execution.duration_ms if context.execution else 0
            return f"[Cron] Job '{job_name}' completed in {duration}ms"

        case HookEvent.JOB_FAIL:
            error = str(context.error) if context.error else "Unknown error"
            return f"[Cron] Job '{job_name}' failed: {error[:200]}"

        case HookEvent.JOB_TIMEOUT:
            timeout = context.job.timeout_sec if context.job else 0
            return f"[Cron] Job '{job_name}' timed out after {timeout}s"

        case HookEvent.JOB_SKIP:
            reason = context.metadata.get("reason", "Unknown")
            return f"[Cron] Job '{job_name}' skipped: {reason}"

        case HookEvent.JOB_RETRY:
            attempt = context.metadata.get("attempt", 0)
            return f"[Cron] Job '{job_name}' retrying (attempt {attempt})"

        case _:
            return f"[Cron] Job '{job_name}': {context.event.value}"


def logging_hook(log_level: str = "info") -> HookHandler:
    """Create a logging hook handler.

    Args:
        log_level: Log level to use.

    Returns:
        Hook handler function.
    """
    log_func = getattr(logger, log_level, logger.info)

    async def handler(context: HookContext) -> None:
        log_data: dict[str, Any] = {
            "event": context.event.value,
            "timestamp": context.timestamp.isoformat(),
        }

        if context.job:
            log_data["job_id"] = str(context.job.id)
            log_data["job_name"] = context.job.name

        if context.execution:
            log_data["execution_id"] = str(context.execution.id)
            log_data["duration_ms"] = context.execution.duration_ms

        if context.error:
            log_data["error"] = str(context.error)
            log_data["error_type"] = type(context.error).__name__

        if context.metadata:
            log_data["metadata"] = context.metadata

        log_func("cron_hook_event", **log_data)

    return handler


def metrics_hook(
    metrics_client: Any,
    prefix: str = "cron",
) -> HookHandler:
    """Create a metrics collection hook handler.

    Args:
        metrics_client: Metrics client with inc/observe methods.
        prefix: Metric name prefix.

    Returns:
        Hook handler function.
    """

    async def handler(context: HookContext) -> None:
        job_name = context.job.name if context.job else "unknown"
        labels = {"job": job_name}

        match context.event:
            case HookEvent.JOB_START:
                if hasattr(metrics_client, "inc"):
                    metrics_client.inc(f"{prefix}_job_starts_total", labels=labels)

            case HookEvent.JOB_COMPLETE:
                if hasattr(metrics_client, "inc"):
                    metrics_client.inc(f"{prefix}_job_completions_total", labels=labels)

                if context.execution and hasattr(metrics_client, "observe"):
                    metrics_client.observe(
                        f"{prefix}_job_duration_ms",
                        context.execution.duration_ms,
                        labels=labels,
                    )

            case HookEvent.JOB_FAIL:
                if hasattr(metrics_client, "inc"):
                    metrics_client.inc(f"{prefix}_job_failures_total", labels=labels)

            case HookEvent.JOB_TIMEOUT:
                if hasattr(metrics_client, "inc"):
                    metrics_client.inc(f"{prefix}_job_timeouts_total", labels=labels)

    return handler
