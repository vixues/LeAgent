"""Base channel framework for LeAgent.

Provides the foundational abstractions for all communication channels,
ensuring uniform message handling, event streaming, and error management.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Optional
from uuid import uuid4

import structlog

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger(__name__)


class ChannelType(str, Enum):
    """Supported channel types for message delivery."""

    CONSOLE = "console"
    WEB = "web"
    DINGTALK = "dingtalk"
    FEISHU = "feishu"
    WECHAT_WORK = "wechat_work"
    API = "api"


class MessageType(str, Enum):
    """Types of messages that can be sent through channels."""

    TEXT = "text"
    MARKDOWN = "markdown"
    IMAGE = "image"
    FILE = "file"
    CARD = "card"
    EVENT = "event"


class MessageStatus(str, Enum):
    """Message delivery status."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


@dataclass
class ChannelMessage:
    """Message model for channel communication.

    Represents a message that can be sent through any channel,
    with support for various content types and metadata.
    """

    id: str = field(default_factory=lambda: str(uuid4()))
    channel_type: ChannelType = ChannelType.CONSOLE
    message_type: MessageType = MessageType.TEXT
    content: str = ""
    sender_id: str = ""
    recipient_id: str = ""
    session_id: str = ""
    status: MessageStatus = MessageStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    sent_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary for serialization."""
        return {
            "id": self.id,
            "channel_type": self.channel_type.value,
            "message_type": self.message_type.value,
            "content": self.content,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "session_id": self.session_id,
            "status": self.status.value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChannelMessage:
        """Create message from dictionary."""
        return cls(
            id=data.get("id", str(uuid4())),
            channel_type=ChannelType(data.get("channel_type", "console")),
            message_type=MessageType(data.get("message_type", "text")),
            content=data.get("content", ""),
            sender_id=data.get("sender_id", ""),
            recipient_id=data.get("recipient_id", ""),
            session_id=data.get("session_id", ""),
            status=MessageStatus(data.get("status", "pending")),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            sent_at=datetime.fromisoformat(data["sent_at"]) if data.get("sent_at") else None,
        )


@dataclass
class ChannelEvent:
    """Event model for channel streaming.

    Represents events that occur during message processing,
    such as typing indicators, delivery confirmations, etc.
    """

    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = "message"
    channel_type: ChannelType = ChannelType.CONSOLE
    session_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "channel_type": self.channel_type.value,
            "session_id": self.session_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


EnqueueCallback = Callable[[Any], None] | None
ProcessHandler = Callable[[Any], "AsyncIterator[Any]"]


class BaseChannel(ABC):
    """Abstract base class for all communication channels.

    Provides a unified interface for message consumption, sending,
    and event streaming across different channel implementations.
    """

    channel_type: ChannelType = ChannelType.CONSOLE
    uses_manager_queue: bool = True

    def __init__(
        self,
        *,
        enabled: bool = True,
        process_handler: ProcessHandler | None = None,
        bot_prefix: str = "",
    ):
        """Initialize base channel.

        Args:
            enabled: Whether this channel is active.
            process_handler: Handler for processing incoming messages.
            bot_prefix: Prefix for bot messages.
        """
        self.enabled = enabled
        self._process_handler = process_handler
        self.bot_prefix = bot_prefix
        self._enqueue: EnqueueCallback = None
        self._running = False

    def set_enqueue(self, callback: EnqueueCallback) -> None:
        """Set the enqueue callback for message queueing.

        Args:
            callback: Callback function to enqueue messages.
        """
        self._enqueue = callback

    def set_process_handler(self, handler: ProcessHandler) -> None:
        """Set the process handler for incoming messages.

        Args:
            handler: Handler function for processing messages.
        """
        self._process_handler = handler

    def resolve_session_id(
        self,
        sender_id: str,
        meta: dict[str, Any] | None = None,
    ) -> str:
        """Resolve session ID from sender and metadata.

        Args:
            sender_id: The sender's identifier.
            meta: Optional metadata for session resolution.

        Returns:
            Resolved session ID.
        """
        return f"{self.channel_type.value}:{sender_id}"

    @abstractmethod
    async def consume_one(self, payload: Any) -> None:
        """Process one message payload from the queue.

        Args:
            payload: The message payload to process.
        """
        ...

    @abstractmethod
    async def send(
        self,
        to_handle: str,
        text: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Send a text message to a recipient.

        Args:
            to_handle: Recipient identifier.
            text: Message text to send.
            meta: Optional metadata for the message.
        """
        ...

    @abstractmethod
    async def send_event(
        self,
        *,
        user_id: str,
        session_id: str,
        event: ChannelEvent,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Send an event to a specific user/session.

        Args:
            user_id: Target user ID.
            session_id: Target session ID.
            event: Event to send.
            meta: Optional metadata.
        """
        ...

    async def send_message(
        self,
        message: ChannelMessage,
    ) -> bool:
        """Send a channel message.

        Args:
            message: The message to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        try:
            await self.send(
                to_handle=message.recipient_id,
                text=message.content,
                meta=message.metadata,
            )
            message.status = MessageStatus.SENT
            message.sent_at = datetime.utcnow()
            return True
        except Exception as e:
            logger.error(
                "Failed to send message",
                channel=self.channel_type.value,
                message_id=message.id,
                error=str(e),
            )
            message.status = MessageStatus.FAILED
            return False

    @abstractmethod
    async def start(self) -> None:
        """Start the channel and begin accepting messages."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel and cleanup resources."""
        ...

    async def health_check(self) -> dict[str, Any]:
        """Check channel health status.

        Returns:
            Health status dictionary.
        """
        return {
            "channel": self.channel_type.value,
            "enabled": self.enabled,
            "running": self._running,
            "healthy": self.enabled and self._running,
        }

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        process_handler: ProcessHandler | None = None,
    ) -> BaseChannel:
        """Create channel instance from configuration.

        Args:
            config: Channel configuration dictionary.
            process_handler: Optional process handler.

        Returns:
            Channel instance.
        """
        raise NotImplementedError("Subclasses must implement from_config")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(type={self.channel_type.value}, enabled={self.enabled})>"
