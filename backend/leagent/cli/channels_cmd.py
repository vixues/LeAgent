"""CLI commands for outbound channel toggles in :func:`leagent.config.config.load_config`."""

from __future__ import annotations

from typing import Any

import click
import yaml

from leagent.cli.utils import (
    console,
    create_table,
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
    prompt_text,
    status_badge,
)
from leagent.config.config import Config, load_config, save_config


CHANNEL_DESCRIPTIONS = {
    "web": "Web UI interface",
    "api": "REST API endpoint",
    "console": "CLI console interface",
    "wechat_work": "WeChat Work (企业微信)",
    "feishu": "Feishu/Lark (飞书)",
    "dingtalk": "DingTalk (钉钉)",
    "email": "Email integration",
    "webhook": "Generic webhook endpoint",
}

CHANNEL_CONFIG_FIELDS = {
    "web": ["endpoint"],
    "api": ["endpoint", "token"],
    "console": [],
    "wechat_work": ["endpoint", "token", "webhook_url"],
    "feishu": ["endpoint", "token", "webhook_url"],
    "dingtalk": ["endpoint", "token", "webhook_url"],
    "email": ["endpoint", "token"],
    "webhook": ["endpoint", "webhook_url"],
}


@click.group(name="channels")
def channels_group() -> None:
    """Toggle channel endpoints in runtime ``config.yaml`` (web, API, DingTalk, Feishu, …)."""


@channels_group.command(name="list")
@click.option("--all", "-a", "show_all", is_flag=True, help="Show all channels including disabled.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def list_channels(show_all: bool, as_json: bool) -> None:
    """List all configured communication channels."""
    config = load_config()
    channels = config.channels

    if as_json:
        channel_data = {
            name: ch.model_dump() for name, ch in channels.items()
        }
        console.print_json(data=channel_data)
        return

    console.print()
    console.rule("[bold cyan]Communication Channels[/]")
    console.print()

    table = create_table(
        columns=[
            ("Channel", {"style": "cyan"}),
            ("Description", {}),
            ("Status", {}),
            ("Endpoint", {}),
        ],
    )

    for name, channel in sorted(channels.items()):
        if not show_all and not channel.enabled:
            continue

        description = CHANNEL_DESCRIPTIONS.get(name, "Custom channel")
        status = status_badge("enabled" if channel.enabled else "disabled")
        endpoint = channel.endpoint or "-"

        table.add_row(name, description, status, endpoint)

    console.print(table)
    console.print()


@channels_group.command(name="enable")
@click.argument("channel")
def enable_channel(channel: str) -> None:
    """Enable a communication channel."""
    config = load_config()

    if channel not in config.channels:
        print_error(f"Channel '{channel}' not found.")
        print_info(f"Available channels: {', '.join(config.channels.keys())}")
        raise click.Abort()

    if config.channels[channel].enabled:
        print_info(f"Channel '{channel}' is already enabled.")
        return

    config.channels[channel].enabled = True
    save_config(config)
    print_success(f"Channel '{channel}' enabled.")


@channels_group.command(name="disable")
@click.argument("channel")
def disable_channel(channel: str) -> None:
    """Disable a communication channel."""
    config = load_config()

    if channel not in config.channels:
        print_error(f"Channel '{channel}' not found.")
        raise click.Abort()

    if not config.channels[channel].enabled:
        print_info(f"Channel '{channel}' is already disabled.")
        return

    config.channels[channel].enabled = False
    save_config(config)
    print_success(f"Channel '{channel}' disabled.")


@channels_group.command(name="config")
@click.argument("channel")
@click.option("--endpoint", "-e", default=None, help="Channel endpoint URL.")
@click.option("--token", "-t", default=None, help="Authentication token.")
@click.option("--webhook-url", "-w", default=None, help="Webhook callback URL.")
@click.option("--set", "-s", "extra_opts", multiple=True, help="Set extra options as key=value.")
@click.option("--interactive", "-i", is_flag=True, help="Configure interactively.")
def config_channel(
    channel: str,
    endpoint: str | None,
    token: str | None,
    webhook_url: str | None,
    extra_opts: tuple[str, ...],
    interactive: bool,
) -> None:
    """Configure a communication channel."""
    config = load_config()

    if channel not in config.channels:
        if not prompt_confirm(f"Channel '{channel}' doesn't exist. Create it?"):
            raise click.Abort()

        from leagent.config.config import ChannelConfig

        config.channels[channel] = ChannelConfig()
        print_info(f"Created new channel '{channel}'")

    channel_config = config.channels[channel]

    if interactive:
        console.print(f"\n[bold]Configuring channel: {channel}[/]\n")

        fields = CHANNEL_CONFIG_FIELDS.get(channel, ["endpoint", "token", "webhook_url"])

        if "endpoint" in fields:
            new_endpoint = prompt_text(
                "Endpoint URL",
                default=channel_config.endpoint or "",
            )
            if new_endpoint:
                channel_config.endpoint = new_endpoint

        if "token" in fields:
            new_token = prompt_text(
                "Authentication token",
                default="",
                password=True,
            )
            if new_token:
                channel_config.token = new_token

        if "webhook_url" in fields:
            new_webhook = prompt_text(
                "Webhook URL",
                default=channel_config.webhook_url or "",
            )
            if new_webhook:
                channel_config.webhook_url = new_webhook

        enable = prompt_confirm("Enable this channel?", default=channel_config.enabled)
        channel_config.enabled = enable

    else:
        if endpoint is not None:
            channel_config.endpoint = endpoint
        if token is not None:
            channel_config.token = token
        if webhook_url is not None:
            channel_config.webhook_url = webhook_url

        for opt in extra_opts:
            if "=" in opt:
                key, value = opt.split("=", 1)
                channel_config.extra[key] = value
            else:
                print_warning(f"Invalid option format: {opt} (expected key=value)")

    save_config(config)
    print_success(f"Channel '{channel}' configuration updated.")

    console.print("\n[dim]Current configuration:[/]")
    console.print(f"  Endpoint: {channel_config.endpoint or '-'}")
    console.print(f"  Token: {'****' if channel_config.token else '-'}")
    console.print(f"  Webhook: {channel_config.webhook_url or '-'}")
    console.print(f"  Enabled: {channel_config.enabled}")


@channels_group.command(name="test")
@click.argument("channel")
@click.option("--message", "-m", default="Test message from LeAgent CLI", help="Test message to send.")
def test_channel(channel: str, message: str) -> None:
    """Test a communication channel by sending a test message."""
    config = load_config()

    if channel not in config.channels:
        print_error(f"Channel '{channel}' not found.")
        raise click.Abort()

    channel_config = config.channels[channel]

    if not channel_config.enabled:
        print_warning(f"Channel '{channel}' is disabled. Enable it first.")

    console.print(f"Testing channel [cyan]{channel}[/]...")

    try:
        _test_channel_connection(channel, channel_config, message)
        print_success(f"Channel '{channel}' test successful.")
    except Exception as e:
        print_error(f"Channel test failed: {e}")
        raise click.Abort()


def _test_channel_connection(channel: str, config: Any, message: str) -> None:
    """Test channel connectivity."""
    import httpx

    if channel == "web":
        print_info("Web channel doesn't require connectivity test.")
        return

    if channel == "api":
        print_info("API channel doesn't require connectivity test.")
        return

    if channel == "console":
        console.print(f"  [dim]Test message:[/] {message}")
        return

    webhook_url = config.webhook_url
    if not webhook_url:
        raise ValueError(f"No webhook URL configured for channel '{channel}'")

    if channel == "dingtalk":
        payload = {
            "msgtype": "text",
            "text": {"content": message},
        }
    elif channel == "feishu":
        payload = {
            "msg_type": "text",
            "content": {"text": message},
        }
    elif channel == "wechat_work":
        payload = {
            "msgtype": "text",
            "text": {"content": message},
        }
    else:
        payload = {"message": message}

    response = httpx.post(webhook_url, json=payload, timeout=10.0)
    response.raise_for_status()

    console.print(f"  [dim]Response:[/] {response.status_code}")


@channels_group.command(name="show")
@click.argument("channel")
def show_channel(channel: str) -> None:
    """Show detailed configuration for a channel."""
    config = load_config()

    if channel not in config.channels:
        print_error(f"Channel '{channel}' not found.")
        raise click.Abort()

    channel_config = config.channels[channel]

    console.print()
    console.rule(f"[bold cyan]Channel: {channel}[/]")
    console.print()

    console.print(f"  [bold]Description:[/] {CHANNEL_DESCRIPTIONS.get(channel, 'Custom channel')}")
    console.print(f"  [bold]Status:[/] {status_badge('enabled' if channel_config.enabled else 'disabled')}")
    console.print()
    console.print("[bold]Configuration:[/]")
    console.print(f"  Endpoint:    {channel_config.endpoint or '-'}")
    console.print(f"  Token:       {'****' + channel_config.token[-4:] if channel_config.token else '-'}")
    console.print(f"  Webhook URL: {channel_config.webhook_url or '-'}")

    if channel_config.extra:
        console.print()
        console.print("[bold]Extra Options:[/]")
        for key, value in channel_config.extra.items():
            console.print(f"  {key}: {value}")

    console.print()
