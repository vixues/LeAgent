"""Channel system for LeAgent.

Provides a unified messaging infrastructure for multiple communication
channels including console, web, DingTalk, Feishu, WeChat Work, and API.
"""

from .base import (
    BaseChannel,
    ChannelEvent,
    ChannelMessage,
    ChannelType,
    EnqueueCallback,
    MessageStatus,
    MessageType,
    ProcessHandler,
)
from .manager import (
    ChannelManager,
    CHANNEL_QUEUE_MAXSIZE,
    CONSUMER_WORKERS_PER_CHANNEL,
)
from .registry import (
    BUILTIN_CHANNEL_KEYS,
    BUILTIN_CHANNEL_SPECS,
    clear_builtin_channel_cache,
    get_channel,
    get_channel_registry,
    list_channels,
    register_channel,
)
from .renderer import (
    MessageRenderer,
    RenderFormat,
    RenderStyle,
    CHANNEL_STYLES,
    markdown_to_plain,
    normalize_dingtalk_markdown,
    normalize_feishu_markdown,
    normalize_wechat_markdown,
)

__all__ = [
    "BaseChannel",
    "BUILTIN_CHANNEL_KEYS",
    "BUILTIN_CHANNEL_SPECS",
    "CHANNEL_QUEUE_MAXSIZE",
    "CHANNEL_STYLES",
    "ChannelEvent",
    "ChannelManager",
    "ChannelMessage",
    "ChannelType",
    "CONSUMER_WORKERS_PER_CHANNEL",
    "EnqueueCallback",
    "MessageRenderer",
    "MessageStatus",
    "MessageType",
    "ProcessHandler",
    "RenderFormat",
    "RenderStyle",
    "clear_builtin_channel_cache",
    "get_channel",
    "get_channel_registry",
    "list_channels",
    "markdown_to_plain",
    "normalize_dingtalk_markdown",
    "normalize_feishu_markdown",
    "normalize_wechat_markdown",
    "register_channel",
]
