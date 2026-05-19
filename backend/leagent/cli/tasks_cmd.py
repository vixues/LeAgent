"""CLI commands for async task inspection.

Uses ``/api/v1/tasks`` on the running monolith (``LEAGENT_API_URL``).
"""

from __future__ import annotations

import time
from typing import Any

import click

from leagent.cli.http import CLIHttpError, get_client, require_server
from leagent.cli.utils import (
    console,
    create_table,
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


@click.group(name="tasks")
def tasks_group() -> None:
    """List and control background tasks via ``/api/v1/tasks`` (server must be running)."""


# ── list ─────────────────────────────────────────────────────────────

@tasks_group.command(name="list")
@click.option("--status", "-s", default=None,
              type=click.Choice(["pending", "queued", "running", "completed", "failed", "cancelled", "paused"]),
              help="Filter by status.")
@click.option("--type", "-t", "task_type", default=None,
              type=click.Choice(["agent", "shell", "workflow", "tool", "cron", "batch", "import", "export", "monitor"]),
              help="Filter by task type.")
@click.option("--limit", "-n", default=20, type=int, help="Max results.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@require_server
def list_tasks(status: str | None, task_type: str | None, limit: int, as_json: bool) -> None:
    """List tasks."""
    client = get_client()
    params: dict[str, Any] = {"page_size": limit}
    if status:
        params["status"] = status
    if task_type:
        params["task_type"] = task_type

    try:
        result = client.get("/api/v1/tasks", params=params)
    except CLIHttpError as e:
        print_error(f"Failed to list tasks: {e}")
        raise click.Abort()

    items = result.get("items", [])
    total = result.get("total", len(items))

    if as_json:
        console.print_json(data=result)
        return

    if not items:
        print_info("No tasks found.")
        return

    console.print()
    console.rule("[bold cyan]Tasks[/]")
    console.print()

    table = create_table(columns=[
        ("ID", {"style": "dim"}),
        ("Name", {"style": "cyan"}),
        ("Type", {}),
        ("Status", {}),
        ("Priority", {}),
        ("Progress", {"justify": "right"}),
        ("Duration", {"justify": "right"}),
        ("Created", {}),
    ])

    for task in items:
        progress = task.get("progress")
        progress_str = f"{progress}%" if progress is not None else "-"
        duration = f"{task.get('duration_ms')}ms" if task.get("duration_ms") else "-"

        table.add_row(
            str(task.get("id", ""))[:8],
            truncate_text(task.get("name", "-"), 30),
            task.get("task_type", "-"),
            status_badge(task.get("status", "-")),
            task.get("priority", "normal"),
            progress_str,
            duration,
            format_timestamp(task.get("created_at")),
        )

    console.print(table)
    console.print()
    console.print(f"[dim]Showing {len(items)} of {total} task(s)[/]")
    console.print()


# ── show ─────────────────────────────────────────────────────────────

@tasks_group.command(name="show")
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@require_server
def show_task(task_id: str, as_json: bool) -> None:
    """Show details of a specific task."""
    client = get_client()

    try:
        task = client.get(f"/api/v1/tasks/{task_id}")
    except CLIHttpError as e:
        print_error(f"Task not found: {e}")
        raise click.Abort()

    if as_json:
        console.print_json(data=task)
        return

    console.print()
    console.rule(f"[bold cyan]Task: {task.get('name')}[/]")
    console.print()

    console.print(f"  [bold]ID:[/]           {task.get('id')}")
    console.print(f"  [bold]Name:[/]         {task.get('name')}")
    console.print(f"  [bold]Type:[/]         {task.get('task_type', '-')}")
    console.print(f"  [bold]Status:[/]       {status_badge(task.get('status', '-'))}")
    console.print(f"  [bold]Priority:[/]     {task.get('priority', 'normal')}")
    console.print(f"  [bold]Description:[/]  {task.get('description') or '-'}")
    console.print()

    console.print("[bold]Execution:[/]")
    console.print(f"  Progress:    {task.get('progress', '-')}%")
    if task.get("progress_message"):
        console.print(f"  Message:     {task['progress_message']}")
    console.print(f"  Duration:    {task.get('duration_ms', '-')}ms")
    console.print(f"  Retries:     {task.get('retry_count', 0)}/{task.get('max_retries', 0)}")
    console.print(f"  Timeout:     {task.get('timeout_seconds', '-')}s")
    console.print()

    if task.get("error"):
        console.print(f"  [bold red]Error:[/] {task['error']}")
        console.print()

    if task.get("model_used"):
        console.print("[bold]Resources:[/]")
        console.print(f"  Model:   {task.get('model_used')}")
        console.print(f"  Tokens:  {task.get('tokens_used', '-')}")
        console.print(f"  Cost:    {task.get('cost', '-')}")
        console.print()

    if task.get("input_data"):
        console.print("[bold]Input:[/]")
        console.print_json(data=task["input_data"])
        console.print()

    if task.get("output_data"):
        console.print("[bold]Output:[/]")
        console.print_json(data=task["output_data"])
        console.print()

    console.print("[bold]Timeline:[/]")
    console.print(f"  Created:    {format_timestamp(task.get('created_at'))}")
    console.print(f"  Started:    {format_timestamp(task.get('started_at'))}")
    console.print(f"  Completed:  {format_timestamp(task.get('completed_at'))}")
    if task.get("scheduled_at"):
        console.print(f"  Scheduled:  {format_timestamp(task.get('scheduled_at'))}")
    console.print()

    console.print("[bold]References:[/]")
    console.print(f"  Flow:    {task.get('flow_id') or '-'}")
    console.print(f"  Session: {task.get('session_id') or '-'}")
    console.print(f"  User:    {task.get('user_id') or '-'}")
    console.print(f"  Parent:  {task.get('parent_id') or '-'}")
    console.print()


# ── kill ─────────────────────────────────────────────────────────────

@tasks_group.command(name="kill")
@click.argument("task_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
@require_server
def kill_task(task_id: str, yes: bool) -> None:
    """Kill a running task."""
    if not yes and not prompt_confirm(f"Kill task {task_id}?"):
        return

    client = get_client()
    try:
        client.post(f"/api/v1/tasks/{task_id}/kill")
        print_success(f"Task {task_id} killed.")
    except CLIHttpError as e:
        print_error(f"Kill failed: {e}")


# ── output ───────────────────────────────────────────────────────────

@tasks_group.command(name="output")
@click.argument("task_id")
@click.option("--follow", "-f", is_flag=True, help="Follow output in real-time.")
@click.option("--offset", default=0, type=int, help="Byte offset to start from.")
@require_server
def task_output(task_id: str, follow: bool, offset: int) -> None:
    """Stream or view task output log."""
    client = get_client()

    current_offset = offset
    try:
        while True:
            try:
                result = client.get(
                    f"/api/v1/tasks/{task_id}/output",
                    params={"offset": current_offset},
                )
            except CLIHttpError as e:
                print_error(f"Failed to read output: {e}")
                return

            content = result.get("content", "")
            if content:
                console.print(content, end="", highlight=False)
                current_offset += len(content.encode("utf-8"))

            done = result.get("done", False)
            if done or not follow:
                if content:
                    console.print()
                if not follow and not content:
                    print_info("No output yet.")
                return

            time.sleep(1)

    except KeyboardInterrupt:
        console.print()


# ── files ────────────────────────────────────────────────────────────

@tasks_group.command(name="files")
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@require_server
def task_files(task_id: str, as_json: bool) -> None:
    """List files produced by a task."""
    client = get_client()

    try:
        result = client.get(f"/api/v1/tasks/{task_id}/files")
    except CLIHttpError as e:
        print_error(f"Failed to list files: {e}")
        raise click.Abort()

    files = result.get("items", result.get("files", []))

    if as_json:
        console.print_json(data=result)
        return

    if not files:
        print_info("No files found for this task.")
        return

    console.print()
    table = create_table(columns=[
        ("ID", {"style": "dim"}),
        ("Name", {"style": "cyan"}),
        ("Type", {}),
        ("Size", {"justify": "right"}),
        ("Status", {}),
    ])

    from leagent.cli.utils import format_bytes

    for f in files:
        table.add_row(
            str(f.get("id", ""))[:8],
            f.get("name", "-"),
            f.get("file_type", f.get("mime_type", "-")),
            format_bytes(f.get("size", 0)),
            status_badge(f.get("status", "-")),
        )

    console.print(table)
    console.print()
