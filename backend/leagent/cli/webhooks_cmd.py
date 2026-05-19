"""CLI commands for outbound webhooks (FastAPI ``/api/v1/webhooks`` CRUD + deliveries)."""

from __future__ import annotations

from typing import Any

import click

from leagent.cli.http import CLIHttpError, get_client, require_server
from leagent.cli.utils import (
    console,
    create_table,
    format_timestamp,
    print_dim,
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
    prompt_text,
    status_badge,
    truncate_text,
)


WEBHOOK_EVENTS = [
    "task.created",
    "task.completed",
    "task.failed",
    "flow.run.started",
    "flow.run.completed",
    "flow.run.failed",
    "message.received",
    "file.uploaded",
    "file.processed",
    "user.created",
    "user.updated",
]


@click.group(name="webhooks")
def webhooks_group() -> None:
    """Outbound webhook subscriptions on ``/api/v1/webhooks`` (requires running server)."""


# ── list ─────────────────────────────────────────────────────────────

@webhooks_group.command(name="list")
@click.option("--all", "-a", "show_all", is_flag=True, help="Show all webhooks including inactive.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@require_server
def list_webhooks(show_all: bool, as_json: bool) -> None:
    """List configured webhook subscriptions."""
    client = get_client()

    try:
        result = client.get("/api/v1/webhooks")
    except CLIHttpError as e:
        print_error(f"Failed to list webhooks: {e}")
        raise click.Abort()

    webhooks = result.get("items", result.get("webhooks", []))

    if as_json:
        console.print_json(data=result)
        return

    if not webhooks:
        print_info("No webhook subscriptions configured.")
        print_dim("Create one with: leagent webhooks add")
        return

    console.print()
    console.rule("[bold cyan]Webhook Subscriptions[/]")
    console.print()

    table = create_table(columns=[
        ("ID", {"style": "dim"}),
        ("Name", {"style": "cyan"}),
        ("URL", {}),
        ("Events", {}),
        ("Status", {}),
        ("Deliveries", {"justify": "right"}),
    ])

    for wh in webhooks:
        st = wh.get("status", "active")
        if not show_all and st == "inactive":
            continue

        events = wh.get("events", [])
        events_str = ", ".join(events[:2])
        if len(events) > 2:
            events_str += f" +{len(events) - 2}"

        table.add_row(
            str(wh.get("id", ""))[:8],
            wh.get("name", "-"),
            truncate_text(wh.get("url", "-"), 40),
            events_str or "-",
            status_badge(st),
            str(wh.get("delivery_count", wh.get("success_count", 0))),
        )

    console.print(table)
    console.print()


# ── show ─────────────────────────────────────────────────────────────

@webhooks_group.command(name="show")
@click.argument("webhook_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@require_server
def show_webhook(webhook_id: str, as_json: bool) -> None:
    """Show details of a webhook subscription."""
    client = get_client()

    try:
        wh = client.get(f"/api/v1/webhooks/{webhook_id}")
    except CLIHttpError as e:
        print_error(f"Webhook not found: {e}")
        raise click.Abort()

    if as_json:
        console.print_json(data=wh)
        return

    console.print()
    console.rule(f"[bold cyan]Webhook: {wh.get('name')}[/]")
    console.print()
    console.print(f"  [bold]ID:[/]          {wh.get('id')}")
    console.print(f"  [bold]Name:[/]        {wh.get('name')}")
    console.print(f"  [bold]URL:[/]         {wh.get('url')}")
    console.print(f"  [bold]Status:[/]      {status_badge(wh.get('status', 'active'))}")
    console.print(f"  [bold]Events:[/]      {', '.join(wh.get('events', []))}")
    console.print(f"  [bold]Secret:[/]      {'****' if wh.get('secret') else '-'}")
    console.print()
    console.print("[bold]Statistics:[/]")
    console.print(f"  Successes:   {wh.get('success_count', 0)}")
    console.print(f"  Failures:    {wh.get('failure_count', 0)}")
    console.print(f"  Last status: {wh.get('last_status_code', '-')}")
    console.print(f"  Last sent:   {format_timestamp(wh.get('last_triggered_at'))}")
    console.print()
    console.print("[bold]Metadata:[/]")
    console.print(f"  Created: {format_timestamp(wh.get('created_at'))}")
    console.print(f"  Updated: {format_timestamp(wh.get('updated_at'))}")
    console.print()


# ── add ──────────────────────────────────────────────────────────────

@webhooks_group.command(name="add")
@click.option("--name", "-n", required=True, help="Webhook name.")
@click.option("--url", "-u", required=True, help="Destination URL.")
@click.option("--events", "-e", required=True, help="Comma-separated events to subscribe to.")
@click.option("--secret", "-s", default=None, help="Signing secret for payload verification.")
@click.option("--enabled/--disabled", default=True, help="Enable immediately.")
@require_server
def add_webhook(name: str, url: str, events: str, secret: str | None, enabled: bool) -> None:
    """Create a new webhook subscription."""
    event_list = [e.strip() for e in events.split(",")]
    invalid = [e for e in event_list if e not in WEBHOOK_EVENTS]
    if invalid:
        print_warning(f"Unknown events: {', '.join(invalid)}")
        print_dim(f"Known events: {', '.join(WEBHOOK_EVENTS)}")

    client = get_client()
    body: dict[str, Any] = {
        "name": name,
        "url": url,
        "events": event_list,
        "status": "active" if enabled else "inactive",
    }
    if secret:
        body["secret"] = secret

    try:
        result = client.post("/api/v1/webhooks", json=body)
        print_success(f"Webhook '{name}' created.")
        console.print(f"  [dim]ID:[/] {result.get('id', 'unknown')}")
    except CLIHttpError as e:
        print_error(f"Failed to create webhook: {e}")
        raise click.Abort()


# ── remove ───────────────────────────────────────────────────────────

@webhooks_group.command(name="remove")
@click.argument("webhook_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
@require_server
def remove_webhook(webhook_id: str, yes: bool) -> None:
    """Remove a webhook subscription."""
    if not yes and not prompt_confirm(f"Remove webhook {webhook_id}?"):
        return

    client = get_client()
    try:
        client.delete(f"/api/v1/webhooks/{webhook_id}")
        print_success(f"Webhook {webhook_id} removed.")
    except CLIHttpError as e:
        print_error(f"Remove failed: {e}")


# ── enable / disable ────────────────────────────────────────────────

@webhooks_group.command(name="enable")
@click.argument("webhook_id")
@require_server
def enable_webhook(webhook_id: str) -> None:
    """Enable a webhook subscription."""
    client = get_client()
    try:
        client.post(f"/api/v1/webhooks/{webhook_id}/enable")
        print_success(f"Webhook {webhook_id} enabled.")
    except CLIHttpError as e:
        print_error(f"Enable failed: {e}")


@webhooks_group.command(name="disable")
@click.argument("webhook_id")
@require_server
def disable_webhook(webhook_id: str) -> None:
    """Disable a webhook subscription."""
    client = get_client()
    try:
        client.post(f"/api/v1/webhooks/{webhook_id}/disable")
        print_success(f"Webhook {webhook_id} disabled.")
    except CLIHttpError as e:
        print_error(f"Disable failed: {e}")


# ── test ─────────────────────────────────────────────────────────────

@webhooks_group.command(name="test")
@click.argument("webhook_id")
@require_server
def test_webhook(webhook_id: str) -> None:
    """Send a test delivery to a webhook endpoint."""
    client = get_client()
    console.print(f"Sending test delivery to webhook [cyan]{webhook_id}[/]...")

    try:
        result = client.post(f"/api/v1/webhooks/{webhook_id}/test")
        status_code = result.get("status_code", result.get("response_status"))
        if status_code and 200 <= status_code < 300:
            print_success(f"Test delivery successful (HTTP {status_code})")
        else:
            print_warning(f"Test delivery returned HTTP {status_code}")
        if result.get("response_time_ms"):
            console.print(f"  [dim]Response time:[/] {result['response_time_ms']}ms")
    except CLIHttpError as e:
        print_error(f"Test failed: {e}")


# ── deliveries ───────────────────────────────────────────────────────

@webhooks_group.command(name="deliveries")
@click.argument("webhook_id")
@click.option("--limit", "-n", default=20, type=int, help="Max results.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@require_server
def list_deliveries(webhook_id: str, limit: int, as_json: bool) -> None:
    """Show recent deliveries for a webhook."""
    client = get_client()

    try:
        result = client.get(
            f"/api/v1/webhooks/{webhook_id}/deliveries",
            params={"limit": limit},
        )
    except CLIHttpError as e:
        print_error(f"Failed to fetch deliveries: {e}")
        raise click.Abort()

    deliveries = result.get("items", result.get("deliveries", []))

    if as_json:
        console.print_json(data=result)
        return

    if not deliveries:
        print_info("No deliveries found.")
        return

    console.print()
    console.rule("[bold cyan]Webhook Deliveries[/]")
    console.print()

    table = create_table(columns=[
        ("ID", {"style": "dim"}),
        ("Event", {}),
        ("Status", {"justify": "right"}),
        ("Response", {"justify": "right"}),
        ("Delivered", {}),
    ])

    for d in deliveries:
        status_code = d.get("status_code", d.get("response_status", "-"))
        success = isinstance(status_code, int) and 200 <= status_code < 300
        status_str = f"[green]{status_code}[/]" if success else f"[red]{status_code}[/]"

        table.add_row(
            str(d.get("id", ""))[:8],
            d.get("event", "-"),
            status_str,
            f"{d.get('response_time_ms', '-')}ms",
            format_timestamp(d.get("delivered_at", d.get("created_at"))),
        )

    console.print(table)
    console.print()
