"""Event manager for typed event callbacks and pub/sub."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from leagent.services.base import Service, ServiceType, service_factory

if TYPE_CHECKING:
    from leagent.config.settings import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
EventCallback = Callable[[Any], Coroutine[Any, Any, None]]


def _run_id_as_uuid(run_id: str | None) -> UUID | None:
    if not run_id:
        return None
    try:
        return UUID(str(run_id))
    except (TypeError, ValueError):
        pass
    try:
        return UUID(hex=str(run_id))
    except (TypeError, ValueError):
        return None


class EventType(str, Enum):
    """Standard event types."""

    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"

    FLOW_STARTED = "flow.started"
    FLOW_NODE_ENTERED = "flow.node.entered"
    FLOW_NODE_COMPLETED = "flow.node.completed"
    FLOW_COMPLETED = "flow.completed"
    FLOW_FAILED = "flow.failed"

    AGENT_MESSAGE = "agent.message"
    AGENT_THINKING = "agent.thinking"
    AGENT_TOOL_CALL = "agent.tool_call"
    AGENT_TOOL_RESULT = "agent.tool_result"
    AGENT_ERROR = "agent.error"

    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_ACTION = "user.action"

    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"

    FILE_UPLOADED = "file.uploaded"
    FILE_DELETED = "file.deleted"

    WEBHOOK_RECEIVED = "webhook.received"
    WEBHOOK_SENT = "webhook.sent"

    CUSTOM = "custom"


class EventPriority(int, Enum):
    """Event processing priority."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class Event(BaseModel, Generic[T]):
    """Base event model."""

    id: UUID = Field(default_factory=uuid4)
    type: EventType | str
    source: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    priority: EventPriority = EventPriority.NORMAL

    data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    correlation_id: UUID | None = None
    user_id: UUID | None = None
    session_id: UUID | None = None


class TaskEvent(Event):
    """Task-related event."""

    task_id: UUID
    task_name: str | None = None
    progress: float | None = None
    error: str | None = None


class FlowEvent(Event):
    """Workflow-related event."""

    flow_id: UUID
    flow_name: str | None = None
    node_id: str | None = None
    node_type: str | None = None


class AgentEvent(Event):
    """Agent-related event."""

    agent_id: str
    message: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: Any | None = None


@dataclass
class Subscription:
    """Event subscription."""

    callback: EventCallback = field(repr=False)
    id: UUID = field(default_factory=uuid4)
    event_type: EventType | str = EventType.CUSTOM
    filter_func: Callable[[Event], bool] | None = field(default=None, repr=False)
    priority: EventPriority = EventPriority.NORMAL
    once: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)


@service_factory(ServiceType.EVENT)
class EventManager(Service):
    """Event manager for typed callbacks and pub/sub.

    Features:
    - Typed event emission and subscription
    - Priority-based callback execution
    - Event filtering
    - One-time subscriptions
    - Async callback support
    - Event history (optional)
    """

    def __init__(
        self,
        settings: Settings,
        *,
        keep_history: bool = False,
        max_history: int = 1000,
    ) -> None:
        super().__init__(settings)
        self._subscriptions: dict[str, list[Subscription]] = defaultdict(list)
        self._all_subscriptions: list[Subscription] = []
        self._keep_history = keep_history
        self._max_history = max_history
        self._history: list[Event] = []
        self._lock = asyncio.Lock()
        self._stats = {
            "events_emitted": 0,
            "callbacks_executed": 0,
            "errors": 0,
        }

    @property
    def name(self) -> str:
        return "EventManager"

    async def _do_health_check(self) -> dict[str, Any]:
        subscription_count = sum(len(subs) for subs in self._subscriptions.values())
        subscription_count += len(self._all_subscriptions)

        return {
            "subscriptions": subscription_count,
            "event_types": len(self._subscriptions),
            "history_size": len(self._history) if self._keep_history else 0,
            "stats": self._stats.copy(),
        }

    def subscribe(
        self,
        event_type: EventType | str,
        callback: EventCallback,
        *,
        filter_func: Callable[[Event], bool] | None = None,
        priority: EventPriority = EventPriority.NORMAL,
        once: bool = False,
    ) -> UUID:
        """Subscribe to events of a specific type.

        Args:
            event_type: Event type to subscribe to
            callback: Async callback function
            filter_func: Optional filter function
            priority: Callback priority
            once: If True, unsubscribe after first event

        Returns:
            Subscription ID for unsubscribing
        """
        subscription = Subscription(
            event_type=event_type,
            callback=callback,
            filter_func=filter_func,
            priority=priority,
            once=once,
        )

        event_key = event_type.value if isinstance(event_type, EventType) else event_type
        self._subscriptions[event_key].append(subscription)

        self._subscriptions[event_key].sort(key=lambda s: s.priority.value, reverse=True)

        logger.debug("Subscribed to %s (id=%s)", event_type, subscription.id)
        return subscription.id

    def subscribe_all(
        self,
        callback: EventCallback,
        *,
        filter_func: Callable[[Event], bool] | None = None,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> UUID:
        """Subscribe to all events.

        Args:
            callback: Async callback function
            filter_func: Optional filter function
            priority: Callback priority

        Returns:
            Subscription ID
        """
        subscription = Subscription(
            event_type="*",
            callback=callback,
            filter_func=filter_func,
            priority=priority,
        )

        self._all_subscriptions.append(subscription)
        self._all_subscriptions.sort(key=lambda s: s.priority.value, reverse=True)

        logger.debug("Subscribed to all events (id=%s)", subscription.id)
        return subscription.id

    def unsubscribe(self, subscription_id: UUID) -> bool:
        """Unsubscribe from events.

        Args:
            subscription_id: The subscription ID

        Returns:
            True if subscription was found and removed
        """
        for event_key, subs in self._subscriptions.items():
            for sub in subs:
                if sub.id == subscription_id:
                    subs.remove(sub)
                    logger.debug("Unsubscribed %s from %s", subscription_id, event_key)
                    return True

        for sub in self._all_subscriptions:
            if sub.id == subscription_id:
                self._all_subscriptions.remove(sub)
                logger.debug("Unsubscribed %s from all events", subscription_id)
                return True

        return False

    async def emit(
        self,
        event: Event,
        *,
        wait: bool = False,
    ) -> None:
        """Emit an event to all subscribers.

        Args:
            event: The event to emit
            wait: If True, wait for all callbacks to complete
        """
        self._stats["events_emitted"] += 1

        if self._keep_history:
            async with self._lock:
                self._history.append(event)
                if len(self._history) > self._max_history:
                    self._history = self._history[-self._max_history:]

        event_key = event.type.value if isinstance(event.type, EventType) else event.type
        subscriptions = list(self._subscriptions.get(event_key, []))
        subscriptions.extend(self._all_subscriptions)

        subscriptions.sort(key=lambda s: s.priority.value, reverse=True)

        to_remove: list[tuple[str, Subscription]] = []
        tasks: list[asyncio.Task] = []

        for sub in subscriptions:
            if sub.filter_func and not sub.filter_func(event):
                continue

            task = asyncio.create_task(self._execute_callback(sub, event))
            tasks.append(task)

            if sub.once:
                to_remove.append((event_key, sub))

        if wait and tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        for event_key, sub in to_remove:
            if event_key == "*":
                if sub in self._all_subscriptions:
                    self._all_subscriptions.remove(sub)
            else:
                if sub in self._subscriptions.get(event_key, []):
                    self._subscriptions[event_key].remove(sub)

    async def _execute_callback(
        self,
        subscription: Subscription,
        event: Event,
    ) -> None:
        """Execute a subscription callback safely."""
        try:
            await subscription.callback(event)
            self._stats["callbacks_executed"] += 1
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(
                "Event callback error for %s (sub=%s): %s",
                event.type,
                subscription.id,
                e,
            )

    async def emit_typed(
        self,
        event_type: EventType | str,
        source: str,
        data: dict[str, Any] | None = None,
        *,
        priority: EventPriority = EventPriority.NORMAL,
        correlation_id: UUID | None = None,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        wait: bool = False,
    ) -> Event:
        """Emit a typed event with convenience parameters.

        Args:
            event_type: Event type
            source: Event source identifier
            data: Event data
            priority: Event priority
            correlation_id: Correlation ID for tracing
            user_id: Associated user ID
            session_id: Associated session ID
            metadata: Additional metadata
            wait: Wait for callbacks

        Returns:
            The emitted event
        """
        event = Event(
            type=event_type,
            source=source,
            data=data or {},
            priority=priority,
            correlation_id=correlation_id,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata or {},
        )

        await self.emit(event, wait=wait)
        return event

    async def emit_task_event(
        self,
        event_type: EventType,
        task_id: UUID,
        source: str,
        *,
        task_name: str | None = None,
        progress: float | None = None,
        error: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> TaskEvent:
        """Emit a task-related event."""
        event = TaskEvent(
            type=event_type,
            source=source,
            task_id=task_id,
            task_name=task_name,
            progress=progress,
            error=error,
            data=data or {},
        )
        await self.emit(event)
        return event

    async def emit_flow_event(
        self,
        event_type: EventType,
        flow_id: UUID,
        source: str,
        *,
        flow_name: str | None = None,
        node_id: str | None = None,
        node_type: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> FlowEvent:
        """Emit a flow-related event."""
        event = FlowEvent(
            type=event_type,
            source=source,
            flow_id=flow_id,
            flow_name=flow_name,
            node_id=node_id,
            node_type=node_type,
            data=data or {},
        )
        await self.emit(event)
        return event

    async def emit_agent_event(
        self,
        event_type: EventType,
        agent_id: str,
        source: str,
        *,
        message: str | None = None,
        tool_name: str | None = None,
        tool_input: dict[str, Any] | None = None,
        tool_output: Any | None = None,
        data: dict[str, Any] | None = None,
    ) -> AgentEvent:
        """Emit an agent-related event."""
        event = AgentEvent(
            type=event_type,
            source=source,
            agent_id=agent_id,
            message=message,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            data=data or {},
        )
        await self.emit(event)
        return event

    async def publish_flow_lifecycle(
        self,
        event_type: EventType,
        *,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Publish a workflow lifecycle event with optional execution trace ids."""
        payload = dict(data or {})
        if run_id:
            payload["run_id"] = run_id
        if parent_run_id:
            payload["parent_run_id"] = parent_run_id
        corr = _run_id_as_uuid(run_id)
        try:
            await self.emit(
                Event(
                    type=event_type,
                    source="workflow",
                    data=payload,
                    correlation_id=corr,
                )
            )
        except Exception:
            logger.debug("flow_event_publish_failed", exc_info=True)

    async def publish_agent_lifecycle(
        self,
        event_type: EventType,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Publish an agent lifecycle event with optional session and trace ids."""
        payload = dict(data or {})
        if session_id:
            payload["session_id"] = session_id
        if run_id:
            payload["run_id"] = run_id
        if parent_run_id:
            payload["parent_run_id"] = parent_run_id
        session_uuid: UUID | None = None
        if session_id:
            try:
                session_uuid = UUID(session_id)
            except (TypeError, ValueError):
                session_uuid = None
        corr = _run_id_as_uuid(run_id)
        try:
            await self.emit(
                Event(
                    type=event_type,
                    source="agent",
                    data=payload,
                    session_id=session_uuid,
                    correlation_id=corr,
                )
            )
        except Exception:
            logger.debug("agent_event_publish_failed", exc_info=True)

    async def bridge_workflow_progress_event(
        self,
        progress_event: Any,
        *,
        run_id: str | None = None,
    ) -> None:
        """Map workflow executor progress events to ``FLOW_*`` event types."""
        etype = getattr(progress_event, "type", "") or ""
        mapping = {
            "execution_start": EventType.FLOW_STARTED,
            "executing": EventType.FLOW_NODE_ENTERED,
            "executed": EventType.FLOW_NODE_COMPLETED,
            "execution_success": EventType.FLOW_COMPLETED,
            "execution_error": EventType.FLOW_FAILED,
            "execution_blocked": EventType.FLOW_NODE_ENTERED,
        }
        mapped = mapping.get(etype)
        if mapped is None:
            return
        data = dict(getattr(progress_event, "data", None) or {})
        data["prompt_id"] = getattr(progress_event, "prompt_id", None)
        data["node_id"] = getattr(progress_event, "node_id", None)
        await self.publish_flow_lifecycle(mapped, run_id=run_id, data=data)

    def get_history(
        self,
        *,
        event_type: EventType | str | None = None,
        limit: int = 100,
        since: datetime | None = None,
    ) -> list[Event]:
        """Get event history.

        Args:
            event_type: Filter by event type
            limit: Maximum events to return
            since: Only events after this time

        Returns:
            List of events (newest first)
        """
        if not self._keep_history:
            return []

        events = list(reversed(self._history))

        if event_type:
            type_str = event_type.value if isinstance(event_type, EventType) else event_type
            events = [e for e in events if (e.type.value if isinstance(e.type, EventType) else e.type) == type_str]

        if since:
            events = [e for e in events if e.timestamp >= since]

        return events[:limit]

    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get event manager statistics."""
        return {
            **self._stats,
            "subscriptions": sum(len(s) for s in self._subscriptions.values()) + len(self._all_subscriptions),
            "event_types": len(self._subscriptions),
        }

    def on(
        self,
        event_type: EventType | str,
        *,
        priority: EventPriority = EventPriority.NORMAL,
        filter_func: Callable[[Event], bool] | None = None,
    ):
        """Decorator for subscribing to events.

        Usage:
            @event_manager.on(EventType.TASK_COMPLETED)
            async def handle_task_completed(event: Event):
                ...
        """

        def decorator(func: EventCallback) -> EventCallback:
            self.subscribe(
                event_type,
                func,
                priority=priority,
                filter_func=filter_func,
            )
            return func

        return decorator

    def once(
        self,
        event_type: EventType | str,
        *,
        priority: EventPriority = EventPriority.NORMAL,
    ):
        """Decorator for one-time event subscription."""

        def decorator(func: EventCallback) -> EventCallback:
            self.subscribe(event_type, func, priority=priority, once=True)
            return func

        return decorator


_event_manager: EventManager | None = None


def get_event_manager() -> EventManager:
    """Get the global event manager instance."""
    if _event_manager is None:
        raise RuntimeError("EventManager not initialized")
    return _event_manager


async def init_event_manager(
    settings: Settings,
    *,
    keep_history: bool = False,
    max_history: int = 1000,
) -> EventManager:
    """Initialize and start the global event manager."""
    global _event_manager
    _event_manager = EventManager(settings, keep_history=keep_history, max_history=max_history)
    await _event_manager.start()
    return _event_manager
