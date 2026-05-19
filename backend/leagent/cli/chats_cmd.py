"""CLI commands for chat session metadata and exports.

Prefers the HTTP API when the monolith is reachable; some helpers fall back to
local files under ``LEAGENT_HOME`` when documented.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import click

from leagent.cli.http import CLIHttpError, get_client, require_server
from leagent.cli.utils import (
    console,
    create_table,
    format_bytes,
    format_duration,
    format_timestamp,
    print_dim,
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
    status_badge,
    truncate_text,
)
from leagent.config.constants import OUTPUT_DIR, LEAGENT_HOME


@click.group(name="chats")
def chats_group() -> None:
    """Manage persisted chat sessions (``SessionManager`` / ``/api/v1/chat/sessions``; server when available)."""


@chats_group.command(name="list")
@click.option("--limit", "-n", default=20, help="Maximum number of chats to show.")
@click.option("--offset", "-o", default=0, help="Number of chats to skip.")
@click.option("--user", "-u", default=None, help="Filter by user ID.")
@click.option("--active/--all", default=False, help="Show only active sessions.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def list_chats(
    limit: int,
    offset: int,
    user: str | None,
    active: bool,
    as_json: bool,
) -> None:
    """List chat sessions."""
    try:
        client = get_client()

        params: dict[str, Any] = {
            "page_size": limit,
            "page": (offset // limit) + 1 if limit else 1,
        }
        if user:
            params["user_id"] = user
        if active:
            params["is_active"] = True

        result = client.get("/api/v1/chat/sessions", params=params)
        chats = result.get("items", result.get("sessions", []))
        total = result.get("total", len(chats))

    except CLIHttpError as e:
        print_warning(f"Could not fetch chats from server: {e}")
        print_info("Showing local chat history instead.")
        chats = _get_local_chats(limit, offset)
        total = len(chats)

    if as_json:
        console.print_json(data={"items": chats, "total": total})
        return

    if not chats:
        print_info("No chat sessions found.")
        return

    console.print()
    console.rule("[bold cyan]Chat Sessions[/]")
    console.print()

    table = create_table(
        columns=[
            ("ID", {"style": "dim"}),
            ("Name", {"style": "cyan"}),
            ("Flow", {}),
            ("Messages", {"justify": "right"}),
            ("Active", {}),
            ("Last Activity", {}),
        ],
    )

    for chat in chats:
        chat_id = str(chat.get("id", ""))[:8]
        name = truncate_text(chat.get("name", chat.get("title", "Untitled")), 35)
        flow_id = str(chat.get("flow_id", ""))[:8] if chat.get("flow_id") else "-"
        message_count = chat.get("message_count", 0)
        is_active = "[green]yes[/]" if chat.get("is_active") else "[dim]no[/]"
        updated = format_timestamp(chat.get("last_message_at", chat.get("updated_at")))

        table.add_row(chat_id, name, flow_id, str(message_count), is_active, updated)

    console.print(table)
    console.print()
    console.print(f"[dim]Showing {len(chats)} of {total} chat(s)[/]")
    console.print()


def _get_local_chats(limit: int, offset: int) -> list[dict[str, Any]]:
    """Get chat sessions from local storage."""
    chats_dir = LEAGENT_HOME / "chats"
    if not chats_dir.exists():
        return []

    chat_files = sorted(
        chats_dir.glob("*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    chats = []
    for chat_file in chat_files[offset : offset + limit]:
        try:
            with open(chat_file, encoding="utf-8") as f:
                chat_data = json.load(f)
            chats.append(chat_data)
        except Exception:
            pass

    return chats


@chats_group.command(name="show")
@click.argument("chat_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def show_chat(chat_id: str, as_json: bool) -> None:
    """Show details of a specific chat session."""
    try:
        client = get_client()
        chat = client.get(f"/api/v1/chat/sessions/{chat_id}")
    except CLIHttpError as e:
        print_warning(f"Could not fetch chat from server: {e}")
        chat = _get_local_chat(chat_id)
        if not chat:
            print_error(f"Chat '{chat_id}' not found.")
            raise click.Abort()

    if as_json:
        console.print_json(data=chat)
        return

    console.print()
    console.rule(f"[bold cyan]Chat: {chat.get('title', 'Untitled')}[/]")
    console.print()

    console.print(f"  [bold]ID:[/]          {chat.get('id')}")
    console.print(f"  [bold]Name:[/]        {chat.get('name', chat.get('title', 'Untitled'))}")
    console.print(f"  [bold]Active:[/]      {chat.get('is_active', '-')}")
    console.print(f"  [bold]Messages:[/]    {chat.get('message_count', 0)}")
    console.print(f"  [bold]Created:[/]     {format_timestamp(chat.get('created_at'))}")
    console.print(f"  [bold]Last msg:[/]    {format_timestamp(chat.get('last_message_at'))}")

    if chat.get("flow_id"):
        console.print(f"  [bold]Flow:[/]        {chat.get('flow_id')}")
    if chat.get("user_id"):
        console.print(f"  [bold]User:[/]        {chat.get('user_id')}")
    if chat.get("session_metadata"):
        console.print(f"  [bold]Metadata:[/]    {chat.get('session_metadata')}")

    messages = chat.get("messages", [])

    if not messages and _server_available_check():
        try:
            client = get_client()
            msg_result = client.get(
                f"/api/v1/chat/sessions/{chat.get('id')}/messages",
                params={"page_size": 10},
            )
            messages = msg_result.get("items", [])
        except CLIHttpError:
            pass

    if messages:
        console.print()
        console.print("[bold]Recent Messages:[/]")
        console.print()

        for msg in messages[-10:]:
            role = msg.get("role", "unknown")
            content = truncate_text(msg.get("content", ""), 100)
            timestamp = format_timestamp(msg.get("created_at"))
            st = msg.get("status", "")
            status_str = f" {status_badge(st)}" if st and st != "completed" else ""

            if role == "user":
                console.print(f"  [cyan]User[/] [{timestamp}]{status_str}:")
            elif role == "assistant":
                console.print(f"  [green]Assistant[/] [{timestamp}]{status_str}:")
            elif role == "tool":
                console.print(f"  [yellow]Tool[/] [{timestamp}]:")
            else:
                console.print(f"  [dim]{role}[/] [{timestamp}]:")

            console.print(f"    {content}")
            if msg.get("model"):
                console.print(f"    [dim]model: {msg['model']}[/]")
            console.print()

    console.print()


def _server_available_check() -> bool:
    try:
        client = get_client()
        return client.health_check()
    except Exception:
        return False


def _get_local_chat(chat_id: str) -> dict[str, Any] | None:
    """Get a specific chat from local storage."""
    chats_dir = LEAGENT_HOME / "chats"

    for chat_file in chats_dir.glob("*.json"):
        if chat_file.stem.startswith(chat_id):
            try:
                with open(chat_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

    return None


@chats_group.command(name="delete")
@click.argument("chat_ids", nargs=-1, required=True)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.option("--all", "delete_all", is_flag=True, help="Delete all chat sessions.")
def delete_chats(chat_ids: tuple[str, ...], yes: bool, delete_all: bool) -> None:
    """Delete one or more chat sessions."""
    if delete_all:
        if not yes and not prompt_confirm("Delete ALL chat sessions? This cannot be undone."):
            print_info("Cancelled.")
            return

        try:
            client = get_client()
            result = client.delete("/api/v1/chat/sessions", params={"all": True})
            deleted = result.get("deleted", 0)
            print_success(f"Deleted {deleted} chat session(s).")
        except CLIHttpError as e:
            print_warning(f"Server deletion failed: {e}")
            _delete_local_chats_all()

        return

    if not chat_ids:
        print_error("No chat IDs provided.")
        raise click.Abort()

    if not yes and not prompt_confirm(f"Delete {len(chat_ids)} chat session(s)?"):
        print_info("Cancelled.")
        return

    deleted_count = 0
    failed_count = 0

    for chat_id in chat_ids:
        try:
            client = get_client()
            client.delete(f"/api/v1/chat/sessions/{chat_id}")
            deleted_count += 1
        except CLIHttpError:
            if _delete_local_chat(chat_id):
                deleted_count += 1
            else:
                failed_count += 1
                print_warning(f"Failed to delete chat '{chat_id}'")

    if deleted_count > 0:
        print_success(f"Deleted {deleted_count} chat session(s).")

    if failed_count > 0:
        print_warning(f"Failed to delete {failed_count} chat session(s).")


def _delete_local_chat(chat_id: str) -> bool:
    """Delete a chat from local storage."""
    chats_dir = LEAGENT_HOME / "chats"

    for chat_file in chats_dir.glob("*.json"):
        if chat_file.stem.startswith(chat_id):
            try:
                chat_file.unlink()
                return True
            except Exception:
                pass

    return False


def _delete_local_chats_all() -> None:
    """Delete all local chat sessions."""
    import shutil

    chats_dir = LEAGENT_HOME / "chats"
    if chats_dir.exists():
        count = len(list(chats_dir.glob("*.json")))
        shutil.rmtree(chats_dir)
        chats_dir.mkdir(parents=True, exist_ok=True)
        print_success(f"Deleted {count} local chat session(s).")


@chats_group.command(name="export")
@click.argument("chat_id", required=False)
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path.")
@click.option("--format", "-f", "output_format", type=click.Choice(["json", "markdown", "txt"]), default="json", help="Export format.")
@click.option("--all", "export_all", is_flag=True, help="Export all chat sessions.")
def export_chats(
    chat_id: str | None,
    output: str | None,
    output_format: str,
    export_all: bool,
) -> None:
    """Export chat sessions to a file."""
    if not chat_id and not export_all:
        print_error("Provide a chat ID or use --all to export all chats.")
        raise click.Abort()

    output_dir = OUTPUT_DIR / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)

    if export_all:
        _export_all_chats(output_dir, output_format, output)
    else:
        _export_single_chat(chat_id, output_format, output)


def _export_single_chat(chat_id: str, output_format: str, output_path: str | None) -> None:
    """Export a single chat session."""
    try:
        client = get_client()
        chat = client.get(f"/api/v1/chat/sessions/{chat_id}")
    except CLIHttpError:
        chat = _get_local_chat(chat_id)
        if not chat:
            print_error(f"Chat '{chat_id}' not found.")
            raise click.Abort()

    if output_path:
        output_file = Path(output_path)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = OUTPUT_DIR / "exports" / f"chat_{chat_id[:8]}_{timestamp}.{output_format}"

    output_file.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "json":
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(chat, f, indent=2, ensure_ascii=False, default=str)

    elif output_format == "markdown":
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"# {chat.get('title', 'Untitled Chat')}\n\n")
            f.write(f"**Created:** {chat.get('created_at', 'Unknown')}\n\n")
            f.write("---\n\n")

            for msg in chat.get("messages", []):
                role = msg.get("role", "unknown").title()
                content = msg.get("content", "")
                f.write(f"### {role}\n\n{content}\n\n")

    elif output_format == "txt":
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"Chat: {chat.get('title', 'Untitled')}\n")
            f.write(f"Created: {chat.get('created_at', 'Unknown')}\n")
            f.write("=" * 50 + "\n\n")

            for msg in chat.get("messages", []):
                role = msg.get("role", "unknown").upper()
                content = msg.get("content", "")
                f.write(f"[{role}]\n{content}\n\n")

    print_success(f"Chat exported to {output_file}")


def _export_all_chats(output_dir: Path, output_format: str, output_path: str | None) -> None:
    """Export all chat sessions."""
    try:
        client = get_client()
        result = client.get("/api/v1/chat/sessions", params={"page_size": 1000})
        chats = result.get("items", result.get("sessions", []))
    except CLIHttpError:
        chats = _get_local_chats(1000, 0)

    if not chats:
        print_info("No chats to export.")
        return

    if output_path:
        output_file = Path(output_path)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"chats_export_{timestamp}.{output_format}"

    output_file.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "json":
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({"chats": chats, "exported_at": datetime.now().isoformat()}, f, indent=2, ensure_ascii=False, default=str)

    elif output_format == "markdown":
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("# Chat Export\n\n")
            f.write(f"**Exported:** {datetime.now().isoformat()}\n\n")
            f.write(f"**Total Chats:** {len(chats)}\n\n")
            f.write("---\n\n")

            for chat in chats:
                f.write(f"## {chat.get('title', 'Untitled')}\n\n")
                f.write(f"ID: {chat.get('id')}\n\n")
                for msg in chat.get("messages", []):
                    role = msg.get("role", "unknown").title()
                    content = msg.get("content", "")
                    f.write(f"### {role}\n\n{content}\n\n")
                f.write("---\n\n")

    elif output_format == "txt":
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"Chat Export - {datetime.now().isoformat()}\n")
            f.write(f"Total Chats: {len(chats)}\n")
            f.write("=" * 50 + "\n\n")

            for chat in chats:
                f.write(f"Chat: {chat.get('title', 'Untitled')}\n")
                f.write(f"ID: {chat.get('id')}\n")
                f.write("-" * 30 + "\n")
                for msg in chat.get("messages", []):
                    role = msg.get("role", "unknown").upper()
                    content = msg.get("content", "")
                    f.write(f"[{role}]\n{content}\n\n")
                f.write("=" * 50 + "\n\n")

    print_success(f"Exported {len(chats)} chat(s) to {output_file}")
