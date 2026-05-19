"""Channel manager for LeAgent.

Manages channel registration, message queues, and channel lifecycle.
Provides centralized control for all communication channels.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from .base import BaseChannel, ChannelEvent, ChannelMessage, ChannelType

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger(__name__)

CHANNEL_QUEUE_MAXSIZE = 1000
CONSUMER_WORKERS_PER_CHANNEL = 4


class ChannelManager:
    """Manager for channel lifecycle and message routing.

    Handles channel registration, per-channel message queues,
    and coordinated startup/shutdown of all channels.
    """

    def __init__(self) -> None:
        """Initialize the channel manager."""
        self._channels: dict[str, BaseChannel] = {}
        self._queues: dict[str, asyncio.Queue[Any]] = {}
        self._consumer_tasks: list[asyncio.Task[None]] = []
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False
        self._health_check_interval = 30.0
        self._health_check_task: asyncio.Task[None] | None = None

    def register(self, channel: BaseChannel) -> None:
        """Register a channel with the manager.

        Args:
            channel: Channel instance to register.

        Raises:
            ValueError: If channel with same type is already registered.
        """
        channel_id = channel.channel_type.value
        if channel_id in self._channels:
            raise ValueError(f"Channel {channel_id} is already registered")

        self._channels[channel_id] = channel
        logger.info("Channel registered", channel=channel_id)

    def unregister(self, channel_type: ChannelType | str) -> BaseChannel | None:
        """Unregister a channel from the manager.

        Args:
            channel_type: Channel type to unregister.

        Returns:
            The unregistered channel, or None if not found.
        """
        channel_id = channel_type.value if isinstance(channel_type, ChannelType) else channel_type
        channel = self._channels.pop(channel_id, None)
        if channel:
            logger.info("Channel unregistered", channel=channel_id)
        return channel

    def get_channel(self, channel_type: ChannelType | str) -> BaseChannel | None:
        """Get a registered channel by type.

        Args:
            channel_type: Channel type to retrieve.

        Returns:
            Channel instance or None if not found.
        """
        channel_id = channel_type.value if isinstance(channel_type, ChannelType) else channel_type
        return self._channels.get(channel_id)

    def list_channels(self) -> list[BaseChannel]:
        """List all registered channels.

        Returns:
            List of registered channel instances.
        """
        return list(self._channels.values())

    def _make_enqueue_callback(self, channel_id: str) -> Callable[[Any], None]:
        """Create an enqueue callback for a specific channel.

        Args:
            channel_id: Channel identifier.

        Returns:
            Enqueue callback function.
        """

        def callback(payload: Any) -> None:
            self.enqueue(channel_id, payload)

        return callback

    def enqueue(self, channel_id: str, payload: Any) -> bool:
        """Enqueue a message for a specific channel.

        Thread-safe method to add messages to channel queues.

        Args:
            channel_id: Target channel identifier.
            payload: Message payload to enqueue.

        Returns:
            True if enqueued successfully, False otherwise.
        """
        queue = self._queues.get(channel_id)
        if not queue:
            logger.warning("No queue for channel", channel=channel_id)
            return False

        if self._loop is None:
            logger.warning("Event loop not available", channel=channel_id)
            return False

        try:
            self._loop.call_soon_threadsafe(self._enqueue_one, channel_id, payload)
            return True
        except RuntimeError as e:
            logger.error("Failed to enqueue message", channel=channel_id, error=str(e))
            return False

    def _enqueue_one(self, channel_id: str, payload: Any) -> None:
        """Internal method to enqueue a single message.

        Args:
            channel_id: Target channel identifier.
            payload: Message payload.
        """
        queue = self._queues.get(channel_id)
        if queue:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Queue full, dropping message", channel=channel_id)

    async def _consume_channel_loop(
        self,
        channel_id: str,
        worker_index: int,
    ) -> None:
        """Consumer loop for processing channel messages.

        Args:
            channel_id: Channel to consume from.
            worker_index: Worker number for logging.
        """
        queue = self._queues.get(channel_id)
        if not queue:
            return

        channel = self._channels.get(channel_id)
        if not channel:
            return

        logger.debug(
            "Consumer started",
            channel=channel_id,
            worker=worker_index,
        )

        while self._running:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=1.0)
                try:
                    await channel.consume_one(payload)
                except Exception:
                    logger.exception(
                        "Error consuming message",
                        channel=channel_id,
                        worker=worker_index,
                    )
                finally:
                    queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(
                    "Unexpected error in consumer loop",
                    channel=channel_id,
                    worker=worker_index,
                )

    async def start_all(self) -> None:
        """Start all registered channels and their consumer loops."""
        if self._running:
            logger.warning("Channel manager already running")
            return

        self._loop = asyncio.get_running_loop()
        self._running = True

        async with self._lock:
            for channel_id, channel in self._channels.items():
                if channel.uses_manager_queue:
                    self._queues[channel_id] = asyncio.Queue(maxsize=CHANNEL_QUEUE_MAXSIZE)
                    channel.set_enqueue(self._make_enqueue_callback(channel_id))

                    for worker_idx in range(CONSUMER_WORKERS_PER_CHANNEL):
                        task = asyncio.create_task(
                            self._consume_channel_loop(channel_id, worker_idx),
                            name=f"channel_consumer_{channel_id}_{worker_idx}",
                        )
                        self._consumer_tasks.append(task)

        for channel_id, channel in self._channels.items():
            try:
                await channel.start()
                logger.info("Channel started", channel=channel_id)
            except Exception:
                logger.exception("Failed to start channel", channel=channel_id)

        self._health_check_task = asyncio.create_task(
            self._health_check_loop(),
            name="channel_health_check",
        )

        logger.info(
            "Channel manager started",
            channels=list(self._channels.keys()),
            queues=list(self._queues.keys()),
        )

    async def stop_all(self) -> None:
        """Stop all channels and cleanup resources."""
        if not self._running:
            return

        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        for task in self._consumer_tasks:
            task.cancel()

        if self._consumer_tasks:
            await asyncio.gather(*self._consumer_tasks, return_exceptions=True)
        self._consumer_tasks.clear()

        async with self._lock:
            for channel_id, channel in reversed(list(self._channels.items())):
                try:
                    await channel.stop()
                    logger.info("Channel stopped", channel=channel_id)
                except Exception:
                    logger.exception("Error stopping channel", channel=channel_id)

            for channel in self._channels.values():
                channel.set_enqueue(None)

        self._queues.clear()
        logger.info("Channel manager stopped")

    async def send_text(
        self,
        *,
        channel: ChannelType | str,
        user_id: str,
        session_id: str,
        text: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Send plain text to a specific channel.

        Args:
            channel: Target channel type.
            user_id: Target user ID.
            session_id: Target session ID.
            text: Text message to send.
            meta: Optional metadata.

        Raises:
            KeyError: If channel is not registered.
        """
        channel_id = channel.value if isinstance(channel, ChannelType) else channel.lower()
        ch = self._channels.get(channel_id)

        if not ch:
            raise KeyError(f"Channel not found: {channel_id}")

        to_handle = f"{channel_id}:{user_id}"
        merged_meta = dict(meta or {})
        merged_meta["session_id"] = session_id
        merged_meta["user_id"] = user_id

        if ch.bot_prefix and "bot_prefix" not in merged_meta:
            merged_meta["bot_prefix"] = ch.bot_prefix

        await ch.send(to_handle, text, merged_meta)
        logger.debug(
            "Text sent",
            channel=channel_id,
            user_id=user_id[:40] if user_id else "",
            session_id=session_id[:40] if session_id else "",
        )

    async def send_event(
        self,
        *,
        channel: ChannelType | str,
        user_id: str,
        session_id: str,
        event: ChannelEvent,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Send an event to a specific channel.

        Args:
            channel: Target channel type.
            user_id: Target user ID.
            session_id: Target session ID.
            event: Event to send.
            meta: Optional metadata.

        Raises:
            KeyError: If channel is not registered.
        """
        channel_id = channel.value if isinstance(channel, ChannelType) else channel.lower()
        ch = self._channels.get(channel_id)

        if not ch:
            raise KeyError(f"Channel not found: {channel_id}")

        merged_meta = dict(meta or {})
        merged_meta["session_id"] = session_id
        merged_meta["user_id"] = user_id

        await ch.send_event(
            user_id=user_id,
            session_id=session_id,
            event=event,
            meta=merged_meta,
        )

    async def broadcast(
        self,
        text: str,
        *,
        channels: list[ChannelType | str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        """Broadcast a message to multiple channels.

        Args:
            text: Message text to broadcast.
            channels: List of channels to broadcast to (all if None).
            meta: Optional metadata.

        Returns:
            Dictionary mapping channel IDs to success status.
        """
        results: dict[str, bool] = {}
        target_channels = channels or list(self._channels.keys())

        for channel in target_channels:
            channel_id = channel.value if isinstance(channel, ChannelType) else channel.lower()
            ch = self._channels.get(channel_id)

            if not ch:
                results[channel_id] = False
                continue

            try:
                await ch.send("broadcast", text, meta)
                results[channel_id] = True
            except Exception as e:
                logger.error(
                    "Broadcast failed",
                    channel=channel_id,
                    error=str(e),
                )
                results[channel_id] = False

        return results

    async def _health_check_loop(self) -> None:
        """Periodic health check for all channels."""
        while self._running:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self._run_health_checks()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in health check loop")

    async def _run_health_checks(self) -> dict[str, dict[str, Any]]:
        """Run health checks on all channels.

        Returns:
            Health status for all channels.
        """
        results: dict[str, dict[str, Any]] = {}

        for channel_id, channel in self._channels.items():
            try:
                results[channel_id] = await channel.health_check()
            except Exception as e:
                results[channel_id] = {
                    "channel": channel_id,
                    "healthy": False,
                    "error": str(e),
                }

        unhealthy = [cid for cid, status in results.items() if not status.get("healthy")]
        if unhealthy:
            logger.warning("Unhealthy channels detected", channels=unhealthy)

        return results

    async def get_health_status(self) -> dict[str, Any]:
        """Get comprehensive health status of the manager.

        Returns:
            Health status dictionary.
        """
        channel_health = await self._run_health_checks()

        return {
            "running": self._running,
            "channels": channel_health,
            "queue_sizes": {cid: q.qsize() for cid, q in self._queues.items()},
            "consumer_tasks": len(self._consumer_tasks),
        }

    async def replace_channel(self, new_channel: BaseChannel) -> None:
        """Replace an existing channel with a new instance.

        Args:
            new_channel: New channel instance to replace with.
        """
        channel_id = new_channel.channel_type.value

        async with self._lock:
            old_channel = self._channels.get(channel_id)

            if channel_id not in self._queues and new_channel.uses_manager_queue:
                self._queues[channel_id] = asyncio.Queue(maxsize=CHANNEL_QUEUE_MAXSIZE)
                for worker_idx in range(CONSUMER_WORKERS_PER_CHANNEL):
                    task = asyncio.create_task(
                        self._consume_channel_loop(channel_id, worker_idx),
                        name=f"channel_consumer_{channel_id}_{worker_idx}",
                    )
                    self._consumer_tasks.append(task)

            new_channel.set_enqueue(self._make_enqueue_callback(channel_id))

            try:
                await new_channel.start()
            except Exception:
                logger.exception("Failed to start new channel", channel=channel_id)
                raise

            self._channels[channel_id] = new_channel

            if old_channel:
                try:
                    await old_channel.stop()
                except Exception:
                    logger.exception("Error stopping old channel", channel=channel_id)

        logger.info("Channel replaced", channel=channel_id)
