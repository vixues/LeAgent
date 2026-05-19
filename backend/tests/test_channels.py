"""Tests for channels system: ChannelMessage, ChannelRegistry, MessageRenderer."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from leagent.channels.base import (
    ChannelMessage,
    ChannelType,
    MessageStatus,
    MessageType,
)


# ===========================================================================
# ChannelMessage
# ===========================================================================


class TestChannelMessage:
    def test_defaults(self) -> None:
        msg = ChannelMessage(content="Hello, world!")
        assert msg.content == "Hello, world!"
        assert msg.channel_type == ChannelType.CONSOLE
        assert msg.message_type == MessageType.TEXT
        assert msg.status == MessageStatus.PENDING

    def test_custom_channel_type(self) -> None:
        msg = ChannelMessage(content="hi", channel_type=ChannelType.WEB)
        assert msg.channel_type == ChannelType.WEB

    def test_unique_ids(self) -> None:
        m1 = ChannelMessage(content="a")
        m2 = ChannelMessage(content="b")
        assert m1.id != m2.id

    def test_to_dict(self) -> None:
        msg = ChannelMessage(content="test", channel_type=ChannelType.API)
        d = msg.to_dict()
        assert d["content"] == "test"
        assert d["channel_type"] == "api"
        assert "id" in d

    def test_markdown_message(self) -> None:
        msg = ChannelMessage(
            content="# Header\n**Bold text**",
            message_type=MessageType.MARKDOWN,
        )
        assert msg.message_type == MessageType.MARKDOWN


# ===========================================================================
# ChannelRegistry
# ===========================================================================


class TestChannelRegistry:
    def test_import_registry_module(self) -> None:
        from leagent.channels import registry
        assert hasattr(registry, "_load_builtin_channels")

    def test_builtin_channel_specs_exist(self) -> None:
        from leagent.channels.registry import BUILTIN_CHANNEL_SPECS
        assert isinstance(BUILTIN_CHANNEL_SPECS, dict)
        assert "console" in BUILTIN_CHANNEL_SPECS

    def test_console_channel_loadable(self) -> None:
        from leagent.channels.console.channel import ConsoleChannel
        assert ConsoleChannel is not None

    def test_builtin_specs_have_correct_format(self) -> None:
        from leagent.channels.registry import BUILTIN_CHANNEL_SPECS
        for key, (module_path, class_name) in BUILTIN_CHANNEL_SPECS.items():
            assert isinstance(module_path, str)
            assert isinstance(class_name, str)


# ===========================================================================
# MessageRenderer
# ===========================================================================


class TestMessageRenderer:
    def test_import(self) -> None:
        from leagent.channels.renderer import MessageRenderer
        assert MessageRenderer is not None

    def test_format_for_console(self) -> None:
        from leagent.channels.renderer import MessageRenderer
        renderer = MessageRenderer()
        formatted = renderer.render("Hello!", MessageType.TEXT)
        assert isinstance(formatted, str)

    def test_format_markdown_for_web(self) -> None:
        from leagent.channels.renderer import MessageRenderer, RenderStyle
        renderer = MessageRenderer(style=RenderStyle(supports_markdown=True))
        formatted = renderer.render("# Header\n**Bold**", MessageType.MARKDOWN)
        assert formatted is not None

    def test_render_text_message(self) -> None:
        from leagent.channels.renderer import MessageRenderer
        renderer = MessageRenderer()
        msg = ChannelMessage(content="Simple text")
        result = renderer.render(msg)
        assert "Simple text" in str(result)


# ===========================================================================
# ConsoleChannel (base channel protocol compliance)
# ===========================================================================


@pytest.mark.asyncio
class TestConsoleChannel:
    async def test_send_message(self) -> None:
        try:
            from leagent.channels.console.channel import ConsoleChannel
        except ImportError:
            pytest.skip("ConsoleChannel not available")

        channel = ConsoleChannel()
        await channel.send("user-1", "test message")

    async def test_channel_type(self) -> None:
        try:
            from leagent.channels.console.channel import ConsoleChannel
        except ImportError:
            pytest.skip("ConsoleChannel not available")

        channel = ConsoleChannel()
        assert hasattr(channel, "channel_type")
