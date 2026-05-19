"""Message renderer for LeAgent channels.

Provides message formatting and conversion between different
channel-specific formats, including markdown transformations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog

from .base import ChannelType, MessageType

logger = structlog.get_logger(__name__)


class RenderFormat(str, Enum):
    """Output format for rendered messages."""

    PLAIN = "plain"
    MARKDOWN = "markdown"
    HTML = "html"
    DINGTALK_MARKDOWN = "dingtalk_markdown"
    FEISHU_MARKDOWN = "feishu_markdown"
    WECHAT_MARKDOWN = "wechat_markdown"


@dataclass
class RenderStyle:
    """Configuration for message rendering style."""

    supports_markdown: bool = True
    supports_code_fence: bool = True
    supports_html: bool = False
    use_emoji: bool = True
    max_length: int = 0
    show_tool_details: bool = True
    filter_tool_messages: bool = False
    filter_thinking: bool = False


CHANNEL_STYLES: dict[ChannelType, RenderStyle] = {
    ChannelType.CONSOLE: RenderStyle(
        supports_markdown=False,
        supports_code_fence=True,
        use_emoji=True,
    ),
    ChannelType.WEB: RenderStyle(
        supports_markdown=True,
        supports_code_fence=True,
        supports_html=True,
        use_emoji=True,
    ),
    ChannelType.DINGTALK: RenderStyle(
        supports_markdown=True,
        supports_code_fence=True,
        max_length=3500,
        use_emoji=True,
    ),
    ChannelType.FEISHU: RenderStyle(
        supports_markdown=True,
        supports_code_fence=True,
        use_emoji=True,
    ),
    ChannelType.WECHAT_WORK: RenderStyle(
        supports_markdown=True,
        supports_code_fence=False,
        max_length=2048,
        use_emoji=True,
    ),
    ChannelType.API: RenderStyle(
        supports_markdown=True,
        supports_code_fence=True,
        supports_html=True,
        use_emoji=True,
    ),
}


class MessageRenderer:
    """Renderer for converting messages between channel formats.

    Handles markdown transformation, truncation, and channel-specific
    formatting requirements.
    """

    def __init__(self, style: RenderStyle | None = None) -> None:
        """Initialize renderer with optional style configuration.

        Args:
            style: Rendering style configuration.
        """
        self.style = style or RenderStyle()

    @classmethod
    def for_channel(cls, channel_type: ChannelType) -> MessageRenderer:
        """Create a renderer configured for a specific channel.

        Args:
            channel_type: Target channel type.

        Returns:
            Configured MessageRenderer instance.
        """
        style = CHANNEL_STYLES.get(channel_type, RenderStyle())
        return cls(style)

    def render(
        self,
        content: str,
        message_type: MessageType = MessageType.TEXT,
        *,
        prefix: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Render content for the configured channel.

        Args:
            content: Raw content to render.
            message_type: Type of message content.
            prefix: Optional prefix to prepend.
            metadata: Optional rendering metadata.

        Returns:
            Rendered content string.
        """
        if not content:
            return prefix

        result = content

        if message_type == MessageType.MARKDOWN:
            result = self._render_markdown(result)
        elif message_type == MessageType.TEXT:
            if not self.style.supports_markdown:
                result = self._strip_markdown(result)

        if prefix:
            result = f"{prefix}{result}"

        if self.style.max_length > 0 and len(result) > self.style.max_length:
            result = self._truncate(result, self.style.max_length)

        return result

    def _render_markdown(self, content: str) -> str:
        """Render markdown content based on channel capabilities.

        Args:
            content: Markdown content.

        Returns:
            Rendered content.
        """
        if not self.style.supports_markdown:
            return self._strip_markdown(content)

        if not self.style.supports_code_fence:
            content = self._convert_code_fences(content)

        return content

    def _strip_markdown(self, content: str) -> str:
        """Remove markdown formatting from content.

        Args:
            content: Markdown content.

        Returns:
            Plain text content.
        """
        content = re.sub(r"\*\*(.+?)\*\*", r"\1", content)
        content = re.sub(r"\*(.+?)\*", r"\1", content)
        content = re.sub(r"__(.+?)__", r"\1", content)
        content = re.sub(r"_(.+?)_", r"\1", content)

        content = re.sub(r"~~(.+?)~~", r"\1", content)

        content = re.sub(r"^#{1,6}\s+", "", content, flags=re.MULTILINE)

        content = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", content)

        content = re.sub(r"^>\s*", "", content, flags=re.MULTILINE)

        content = re.sub(r"^[-*+]\s+", "- ", content, flags=re.MULTILINE)

        return content

    def _convert_code_fences(self, content: str) -> str:
        """Convert code fences to alternative format.

        Args:
            content: Content with code fences.

        Returns:
            Content with converted code blocks.
        """

        def replace_code_block(match: re.Match[str]) -> str:
            lang = match.group(1) or ""
            code = match.group(2)
            if lang:
                return f"[{lang}]\n{code}"
            return code

        pattern = r"```(\w*)\n?([\s\S]*?)```"
        return re.sub(pattern, replace_code_block, content)

    def _truncate(self, content: str, max_length: int) -> str:
        """Truncate content to maximum length with ellipsis.

        Args:
            content: Content to truncate.
            max_length: Maximum allowed length.

        Returns:
            Truncated content.
        """
        if len(content) <= max_length:
            return content

        suffix = "..."
        return content[: max_length - len(suffix)] + suffix

    def format_tool_call(
        self,
        name: str,
        arguments: str | dict[str, Any],
        *,
        show_details: bool | None = None,
    ) -> str:
        """Format a tool call for display.

        Args:
            name: Tool name.
            arguments: Tool arguments.
            show_details: Whether to show argument details.

        Returns:
            Formatted tool call string.
        """
        show = show_details if show_details is not None else self.style.show_tool_details

        if isinstance(arguments, dict):
            import json

            args_str = json.dumps(arguments, ensure_ascii=False, indent=2)
        else:
            args_str = str(arguments)

        if not show:
            args_preview = "..."
        elif len(args_str) > 200:
            args_preview = args_str[:200] + "..."
        else:
            args_preview = args_str

        if self.style.supports_markdown and self.style.use_emoji:
            return f"🔧 **{name}**\n```\n{args_preview}\n```"
        if self.style.supports_markdown:
            return f"**{name}**\n```\n{args_preview}\n```"
        if self.style.supports_code_fence:
            return f"{name}\n```\n{args_preview}\n```"
        return f"{name}: {args_preview}"

    def format_tool_output(
        self,
        name: str,
        output: Any,
        *,
        show_details: bool | None = None,
    ) -> str:
        """Format a tool output for display.

        Args:
            name: Tool name.
            output: Tool output.
            show_details: Whether to show output details.

        Returns:
            Formatted tool output string.
        """
        show = show_details if show_details is not None else self.style.show_tool_details

        if isinstance(output, (dict, list)):
            import json

            output_str = json.dumps(output, ensure_ascii=False, indent=2)
        else:
            output_str = str(output)

        if not show:
            output_preview = "..."
        elif len(output_str) > 500:
            output_preview = output_str[:500] + "..."
        else:
            output_preview = output_str

        label = self._format_tool_output_label(name)

        if self.style.supports_code_fence:
            return f"{label}\n```\n{output_preview}\n```"
        return f"{label}\n{output_preview}"

    def _format_tool_output_label(self, name: str) -> str:
        """Format tool output label.

        Args:
            name: Tool name.

        Returns:
            Formatted label.
        """
        if self.style.use_emoji:
            return f"✅ **{name}**:"
        if self.style.supports_markdown:
            return f"**{name}**:"
        return f"{name}:"

    def format_error(self, error: str, *, prefix: str = "") -> str:
        """Format an error message.

        Args:
            error: Error message.
            prefix: Optional prefix.

        Returns:
            Formatted error string.
        """
        if self.style.use_emoji:
            return f"{prefix}❌ Error: {error}"
        return f"{prefix}Error: {error}"


def normalize_dingtalk_markdown(text: str) -> str:
    """Normalize markdown for DingTalk compatibility.

    DingTalk has specific markdown requirements that differ
    from standard markdown.

    Args:
        text: Input markdown text.

    Returns:
        DingTalk-compatible markdown.
    """
    text = re.sub(r"\n{3,}", "\n\n", text)

    text = re.sub(r"^(#{1,6})\s*", r"\1 ", text, flags=re.MULTILINE)

    text = re.sub(r"\n(#{1,6})", r"\n\n\1", text)

    return text.strip()


def normalize_feishu_markdown(text: str) -> str:
    """Normalize markdown for Feishu/Lark compatibility.

    Feishu has its own markdown dialect with specific requirements.

    Args:
        text: Input markdown text.

    Returns:
        Feishu-compatible markdown.
    """
    text = re.sub(r"\*\*(.+?)\*\*", r"**\1**", text)
    text = re.sub(r"~~(.+?)~~", r"~~\1~~", text)

    return text.strip()


def normalize_wechat_markdown(text: str) -> str:
    """Normalize markdown for WeChat Work compatibility.

    WeChat Work supports a limited subset of markdown.

    Args:
        text: Input markdown text.

    Returns:
        WeChat Work-compatible markdown.
    """
    def replace_code_block(match: re.Match[str]) -> str:
        code = match.group(2)
        return f"\n{code}\n"

    text = re.sub(r"```(\w*)\n?([\s\S]*?)```", replace_code_block, text)

    text = re.sub(r"`([^`]+)`", r'"\1"', text)

    return text.strip()


def markdown_to_plain(text: str) -> str:
    """Convert markdown to plain text.

    Args:
        text: Markdown text.

    Returns:
        Plain text without markdown formatting.
    """
    renderer = MessageRenderer(RenderStyle(supports_markdown=False))
    return renderer._strip_markdown(text)
