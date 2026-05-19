"""Console channel implementation for LeAgent.

A lightweight channel that prints agent responses to stdout and
maintains an in-memory push store for API access.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import deque
from datetime import datetime
from typing import Any

import structlog

from ..base import (
    BaseChannel,
    ChannelEvent,
    ChannelMessage,
    ChannelType,
    MessageStatus,
    MessageType,
)
from ..renderer import MessageRenderer, RenderStyle

logger = structlog.get_logger(__name__)

_USE_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

_GREEN = "\033[32m" if _USE_COLOR else ""
_YELLOW = "\033[33m" if _USE_COLOR else ""
_RED = "\033[31m" if _USE_COLOR else ""
_BOLD = "\033[1m" if _USE_COLOR else ""
_RESET = "\033[0m" if _USE_COLOR else ""


class ConsolePushStore:
    """In-memory store for push messages accessible via API.

    Thread-safe store that maintains a bounded queue of messages
    per session for retrieval via GET /console/push-messages.
    """

    def __init__(self, max_messages_per_session: int = 100) -> None:
        """Initialize push store.

        Args:
            max_messages_per_session: Maximum messages to retain per session.
        """
        self._store: dict[str, deque[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        self._max_per_session = max_messages_per_session

    async def append(
        self,
        session_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append a message to the session store.

        Args:
            session_id: Session identifier.
            content: Message content.
            metadata: Optional message metadata.
        """
        async with self._lock:
            if session_id not in self._store:
                self._store[session_id] = deque(maxlen=self._max_per_session)

            self._store[session_id].append(
                {
                    "content": content,
                    "timestamp": datetime.utcnow().isoformat(),
                    "metadata": metadata or {},
                }
            )

    async def get_messages(
        self,
        session_id: str,
        *,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get messages for a session.

        Args:
            session_id: Session identifier.
            since: Optional timestamp filter.
            limit: Maximum messages to return.

        Returns:
            List of messages.
        """
        async with self._lock:
            messages = list(self._store.get(session_id, []))

        if since:
            since_iso = since.isoformat()
            messages = [m for m in messages if m["timestamp"] > since_iso]

        if limit:
            messages = messages[-limit:]

        return messages

    async def clear_session(self, session_id: str) -> None:
        """Clear all messages for a session.

        Args:
            session_id: Session identifier.
        """
        async with self._lock:
            self._store.pop(session_id, None)

    async def get_all_sessions(self) -> list[str]:
        """Get all session IDs with stored messages.

        Returns:
            List of session IDs.
        """
        async with self._lock:
            return list(self._store.keys())


_push_store = ConsolePushStore()


async def get_push_store() -> ConsolePushStore:
    """Get the global push store instance.

    Returns:
        Push store instance.
    """
    return _push_store


class ConsoleChannel(BaseChannel):
    """Console channel for terminal-based interaction.

    Prints agent responses to stdout with color formatting
    and maintains messages in a push store for API access.
    """

    channel_type = ChannelType.CONSOLE
    uses_manager_queue = True

    def __init__(
        self,
        *,
        enabled: bool = True,
        bot_prefix: str = "[BOT] ",
        show_timestamps: bool = True,
        use_colors: bool = True,
        process_handler: Any | None = None,
    ) -> None:
        """Initialize console channel.

        Args:
            enabled: Whether channel is active.
            bot_prefix: Prefix for bot messages.
            show_timestamps: Whether to show timestamps.
            use_colors: Whether to use ANSI colors.
            process_handler: Message processing handler.
        """
        super().__init__(
            enabled=enabled,
            bot_prefix=bot_prefix,
            process_handler=process_handler,
        )
        self.show_timestamps = show_timestamps
        self.use_colors = use_colors and _USE_COLOR
        self._renderer = MessageRenderer(
            RenderStyle(
                supports_markdown=False,
                supports_code_fence=True,
                use_emoji=True,
            )
        )

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        process_handler: Any | None = None,
    ) -> ConsoleChannel:
        """Create console channel from configuration.

        Args:
            config: Configuration dictionary.
            process_handler: Message processing handler.

        Returns:
            ConsoleChannel instance.
        """
        return cls(
            enabled=config.get("enabled", True),
            bot_prefix=config.get("bot_prefix", "[BOT] "),
            show_timestamps=config.get("show_timestamps", True),
            use_colors=config.get("use_colors", True),
            process_handler=process_handler,
        )

    @classmethod
    def from_env(cls, process_handler: Any | None = None) -> ConsoleChannel:
        """Create console channel from environment variables.

        Args:
            process_handler: Message processing handler.

        Returns:
            ConsoleChannel instance.
        """
        return cls(
            enabled=os.getenv("CONSOLE_CHANNEL_ENABLED", "1") == "1",
            bot_prefix=os.getenv("CONSOLE_BOT_PREFIX", "[BOT] "),
            show_timestamps=os.getenv("CONSOLE_SHOW_TIMESTAMPS", "1") == "1",
            use_colors=os.getenv("CONSOLE_USE_COLORS", "1") == "1",
            process_handler=process_handler,
        )

    def _timestamp(self) -> str:
        """Get formatted timestamp.

        Returns:
            Formatted timestamp string.
        """
        return datetime.now().strftime("%H:%M:%S")

    def _format_output(
        self,
        text: str,
        *,
        prefix: str = "",
        color: str = "",
        label: str = "",
    ) -> str:
        """Format output with optional color and prefix.

        Args:
            text: Text to format.
            prefix: Optional prefix.
            color: ANSI color code.
            label: Label for the message.

        Returns:
            Formatted string.
        """
        parts = []

        if self.show_timestamps:
            ts = self._timestamp()
            if self.use_colors:
                parts.append(f"{color}{_BOLD}[{ts}]{_RESET}")
            else:
                parts.append(f"[{ts}]")

        if label:
            if self.use_colors:
                parts.append(f"{color}{_BOLD}{label}{_RESET}")
            else:
                parts.append(label)

        parts.append(f"{prefix}{text}")

        return " ".join(parts)

    def _print_message(
        self,
        text: str,
        *,
        msg_type: str = "bot",
        prefix: str | None = None,
    ) -> None:
        """Print a message to stdout.

        Args:
            text: Message text.
            msg_type: Message type (bot, error, info).
            prefix: Optional prefix override.
        """
        if not self.enabled:
            return

        actual_prefix = prefix if prefix is not None else self.bot_prefix

        if msg_type == "bot":
            color = _GREEN
            label = "Bot"
            emoji = "🤖"
        elif msg_type == "error":
            color = _RED
            label = "Error"
            emoji = "❌"
        elif msg_type == "info":
            color = _YELLOW
            label = "Info"
            emoji = "ℹ️"
        else:
            color = ""
            label = ""
            emoji = ""

        if self.use_colors and emoji:
            label = f"{emoji} {label}"

        formatted = self._format_output(
            text,
            prefix=actual_prefix,
            color=color,
            label=label,
        )

        print(f"\n{formatted}\n")

    async def consume_one(self, payload: Any) -> None:
        """Process one message from the queue.

        Args:
            payload: Message payload to process.
        """
        if not self.enabled:
            return

        if isinstance(payload, ChannelMessage):
            await self._process_channel_message(payload)
        elif isinstance(payload, dict):
            await self._process_dict_payload(payload)
        else:
            logger.warning("Unknown payload type", payload_type=type(payload).__name__)

    async def _process_channel_message(self, message: ChannelMessage) -> None:
        """Process a ChannelMessage.

        Args:
            message: Message to process.
        """
        if self._process_handler:
            try:
                async for event in self._process_handler(message):
                    await self._handle_event(event, message.session_id)
            except Exception:
                logger.exception("Error processing message")
                self._print_message("An error occurred while processing.", msg_type="error")
        else:
            self._print_message(message.content)

    async def _process_dict_payload(self, payload: dict[str, Any]) -> None:
        """Process a dictionary payload.

        Args:
            payload: Dictionary payload.
        """
        content = payload.get("content", "")
        session_id = payload.get("session_id", "")

        if content:
            self._print_message(content)

            if session_id:
                await _push_store.append(session_id, content, payload.get("metadata"))

    async def _handle_event(self, event: Any, session_id: str) -> None:
        """Handle an event from the process handler.

        Args:
            event: Event to handle.
            session_id: Current session ID.
        """
        if isinstance(event, ChannelEvent):
            self._print_message(
                str(event.data.get("content", "")),
                msg_type="info" if event.event_type != "message" else "bot",
            )

    async def send(
        self,
        to_handle: str,
        text: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Send a text message.

        Args:
            to_handle: Recipient identifier.
            text: Message text.
            meta: Optional metadata.
        """
        if not self.enabled:
            return

        prefix = (meta or {}).get("bot_prefix", self.bot_prefix)
        self._print_message(text, prefix=prefix)

        session_id = (meta or {}).get("session_id")
        if session_id and text.strip():
            await _push_store.append(session_id, text.strip(), meta)

    async def send_event(
        self,
        *,
        user_id: str,
        session_id: str,
        event: ChannelEvent,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Send an event.

        Args:
            user_id: Target user ID.
            session_id: Target session ID.
            event: Event to send.
            meta: Optional metadata.
        """
        if not self.enabled:
            return

        content = event.data.get("content", "")
        if content:
            self._print_message(
                str(content),
                msg_type="info" if event.event_type != "message" else "bot",
            )

            if session_id:
                await _push_store.append(session_id, str(content), meta)

    async def start(self) -> None:
        """Start the console channel."""
        if not self.enabled:
            logger.debug("Console channel disabled")
            return

        self._running = True
        logger.info("Console channel started")

    async def stop(self) -> None:
        """Stop the console channel."""
        if not self.enabled:
            return

        self._running = False
        logger.info("Console channel stopped")

    async def health_check(self) -> dict[str, Any]:
        """Check channel health.

        Returns:
            Health status dictionary.
        """
        return {
            "channel": self.channel_type.value,
            "enabled": self.enabled,
            "running": self._running,
            "healthy": self.enabled,
            "push_store_sessions": len(await _push_store.get_all_sessions()),
        }
