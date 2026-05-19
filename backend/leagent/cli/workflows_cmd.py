"""CLI commands for workflow flows and executions.

Talks to the FastAPI workflow router (``/api/v1/workflow/flows``, run endpoints, …).
Requires ``leagent run`` (or a remote ``LEAGENT_API_URL``) unless a command documents otherwise.
"""

from __future__ import annotations

import json
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


@click.group(name="workflows")
def workflows_group() -> None:
    """Manage YAML/ReactFlow flows and executions via ``/api/v1/workflow/*`` (server must be running)."""


# ── list flows ───────────────────────────────────────────────────────

@workflows_group.command(name="list")
@click.option("--type", "-t", "flow_type", default=None,
              type=click.Choice(["agent", "workflow", "chat", "tool"]),
              help="Filter by flow type.")
@click.option("--status", "-s", default=None,
              type=click.Choice(["draft", "published", "archived"]),
              help="Filter by status.")
@click.option("--limit", "-n", default=20, type=int, help="Max results.")
@click.option("--search", "-q", default=None, help="Search by name.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@require_server
def list_flows(
    flow_type: str | None,
    status: str | None,
    limit: int,
    search: str | None,
    as_json: bool,
) -> None:
    """List flows (agents, workflows, tools, chats)."""
    client = get_client()
    params: dict[str, Any] = {"page_size": limit}
    if flow_type:
        params["flow_type"] = flow_type
    if status:
        params["status"] = status
    if search:
        params["search"] = search

    try:
        result = client.get("/api/v1/workflow/flows", params=params)
    except CLIHttpError as e:
        print_error(f"Failed to list flows: {e}")
        raise click.Abort()

    items = result.get("items", [])
    total = result.get("total", len(items))

    if as_json:
        console.print_json(data=result)
        return

    if not items:
        print_info("No flows found.")
        return

    console.print()
    console.rule("[bold cyan]Flows[/]")
    console.print()

    table = create_table(columns=[
        ("ID", {"style": "dim"}),
        ("Name", {"style": "cyan"}),
        ("Type", {}),
        ("Status", {}),
        ("Runs", {"justify": "right"}),
        ("Updated", {}),
    ])

    for flow in items:
        table.add_row(
            str(flow.get("id", ""))[:8],
            truncate_text(flow.get("name", "-"), 40),
            flow.get("flow_type", "-"),
            status_badge(flow.get("status", "draft")),
            str(flow.get("run_count", 0)),
            format_timestamp(flow.get("updated_at")),
        )

    console.print(table)
    console.print()
    console.print(f"[dim]Showing {len(items)} of {total} flow(s)[/]")
    console.print()


# ── show flow ────────────────────────────────────────────────────────

@workflows_group.command(name="show")
@click.argument("flow_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@require_server
def show_flow(flow_id: str, as_json: bool) -> None:
    """Show details of a specific flow."""
    client = get_client()

    try:
        flow = client.get(f"/api/v1/workflow/flows/{flow_id}")
    except CLIHttpError as e:
        print_error(f"Flow not found: {e}")
        raise click.Abort()

    if as_json:
        console.print_json(data=flow)
        return

    console.print()
    console.rule(f"[bold cyan]Flow: {flow.get('name')}[/]")
    console.print()

    console.print(f"  [bold]ID:[/]          {flow.get('id')}")
    console.print(f"  [bold]Name:[/]        {flow.get('name')}")
    console.print(f"  [bold]Type:[/]        {flow.get('flow_type', '-')}")
    console.print(f"  [bold]Status:[/]      {status_badge(flow.get('status', 'draft'))}")
    console.print(f"  [bold]Description:[/] {flow.get('description') or '-'}")
    console.print(f"  [bold]Public:[/]      {flow.get('is_public', False)}")
    console.print(f"  [bold]Tags:[/]        {flow.get('tags') or '-'}")
    console.print(f"  [bold]Version:[/]     {flow.get('version', 1)}")
    console.print()
    console.print("[bold]Statistics:[/]")
    console.print(f"  Run count:    {flow.get('run_count', 0)}")
    console.print(f"  Last run:     {format_timestamp(flow.get('last_run_at'))}")
    console.print(f"  Avg run time: {flow.get('avg_run_time_ms', '-')}ms")
    console.print()
    console.print("[bold]Metadata:[/]")
    console.print(f"  Created:  {format_timestamp(flow.get('created_at'))}")
    console.print(f"  Updated:  {format_timestamp(flow.get('updated_at'))}")
    console.print(f"  Owner:    {flow.get('user_id', '-')}")
    console.print(f"  Folder:   {flow.get('folder_id') or '-'}")
    if flow.get("endpoint_name"):
        console.print(f"  Endpoint: {flow.get('endpoint_name')}")
    console.print()


# ── run flow / workflow ──────────────────────────────────────────────

@workflows_group.command(name="run")
@click.argument("flow_id")
@click.option("--input", "-i", "input_file", type=click.Path(exists=True), help="Input JSON file.")
@click.option("--param", "-p", multiple=True, help="Parameters as key=value pairs.")
@click.option("--wait/--no-wait", default=True, help="Wait for completion (default: yes).")
@click.option("--json", "as_json", is_flag=True, help="Output result as JSON.")
@require_server
def run_flow(
    flow_id: str,
    input_file: str | None,
    param: tuple[str, ...],
    wait: bool,
    as_json: bool,
) -> None:
    """Execute a flow or workflow by ID."""
    inputs: dict[str, Any] = {}
    if input_file:
        with open(input_file, encoding="utf-8") as f:
            inputs = json.load(f)
    for p in param:
        if "=" in p:
            key, value = p.split("=", 1)
            inputs[key] = value

    console.print(f"Running flow [cyan]{flow_id}[/]...")

    client = get_client()
    try:
        result = client.post(
            f"/api/v1/workflow/flows/{flow_id}/run",
            json={"inputs": inputs},
        )
    except CLIHttpError as e:
        print_error(f"Execution failed: {e}")
        raise click.Abort()

    execution_id = result.get("execution_id", result.get("id"))

    if as_json:
        console.print_json(data=result)
        return

    if execution_id:
        print_success(f"Execution started: {execution_id}")

        if wait:
            _poll_execution(flow_id, str(execution_id))
    else:
        print_success("Flow executed.")
        if result.get("outputs"):
            console.print_json(data=result["outputs"])


def _poll_execution(flow_id: str, execution_id: str) -> None:
    import time

    client = get_client()
    terminal = {"completed", "failed", "cancelled", "error"}

    with console.status("[dim]Waiting for execution...[/]"):
        for _ in range(180):
            try:
                ex = client.get(f"/api/v1/workflow/flows/{flow_id}/executions/{execution_id}")
                st = ex.get("status", "")
                if st in terminal:
                    console.print()
                    if st == "completed":
                        print_success(f"Completed in {ex.get('duration_ms', '?')}ms")
                        if ex.get("outputs"):
                            console.print_json(data=ex["outputs"])
                    else:
                        print_error(f"Execution {st}: {ex.get('error', '-')}")
                    return
            except CLIHttpError:
                pass
            time.sleep(2)

    print_warning("Timed out. Check execution status manually.")


# ── executions ───────────────────────────────────────────────────────

@workflows_group.command(name="executions")
@click.argument("flow_id", required=False)
@click.option("--limit", "-n", default=20, type=int, help="Max results.")
@click.option("--status", "-s", default=None, help="Filter by status.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@require_server
def list_executions(flow_id: str | None, limit: int, status: str | None, as_json: bool) -> None:
    """List workflow executions, optionally filtered by flow ID."""
    client = get_client()
    params: dict[str, Any] = {"limit": limit}
    if status:
        params["status"] = status

    try:
        if flow_id:
            result = client.get(f"/api/v1/workflow/flows/{flow_id}/executions", params=params)
        else:
            result = client.get("/api/v1/workflow/flows/executions", params=params)
    except CLIHttpError as e:
        print_error(f"Failed to list executions: {e}")
        raise click.Abort()

    items = result.get("items", result.get("executions", []))

    if as_json:
        console.print_json(data=result)
        return

    if not items:
        print_info("No executions found.")
        return

    console.print()
    console.rule("[bold cyan]Workflow Executions[/]")
    console.print()

    table = create_table(columns=[
        ("ID", {"style": "dim"}),
        ("Flow", {"style": "cyan"}),
        ("Status", {}),
        ("Trigger", {}),
        ("Nodes", {"justify": "right"}),
        ("Duration", {"justify": "right"}),
        ("Started", {}),
    ])

    for ex in items:
        table.add_row(
            str(ex.get("id", ""))[:8],
            str(ex.get("flow_id", ""))[:8],
            status_badge(ex.get("status", "-")),
            ex.get("trigger_type", "-"),
            str(ex.get("node_count", 0)),
            f"{ex.get('duration_ms', 0)}ms" if ex.get("duration_ms") else "-",
            format_timestamp(ex.get("started_at", ex.get("created_at"))),
        )

    console.print(table)
    console.print()


# ── execution detail ─────────────────────────────────────────────────

@workflows_group.command(name="execution")
@click.argument("flow_id")
@click.argument("execution_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@require_server
def show_execution(flow_id: str, execution_id: str, as_json: bool) -> None:
    """Show details of a specific workflow execution."""
    client = get_client()

    try:
        ex = client.get(f"/api/v1/workflow/flows/{flow_id}/executions/{execution_id}")
    except CLIHttpError as e:
        print_error(f"Execution not found: {e}")
        raise click.Abort()

    if as_json:
        console.print_json(data=ex)
        return

    console.print()
    console.rule(f"[bold cyan]Execution: {str(ex.get('id', ''))[:8]}[/]")
    console.print()
    console.print(f"  [bold]ID:[/]          {ex.get('id')}")
    console.print(f"  [bold]Flow ID:[/]     {ex.get('flow_id')}")
    console.print(f"  [bold]Status:[/]      {status_badge(ex.get('status', '-'))}")
    console.print(f"  [bold]Trigger:[/]     {ex.get('trigger_type', '-')}")
    console.print(f"  [bold]Current node:[/] {ex.get('current_node', '-')}")
    console.print(f"  [bold]Node count:[/]  {ex.get('node_count', 0)}")
    console.print(f"  [bold]Duration:[/]    {ex.get('duration_ms', '-')}ms")
    console.print(f"  [bold]Retries:[/]     {ex.get('retry_count', 0)}")
    console.print()

    if ex.get("error"):
        console.print(f"  [bold red]Error:[/] {ex['error']}")
        if ex.get("error_stack"):
            console.print(f"  [dim]{truncate_text(ex['error_stack'], 200)}[/]")
        console.print()

    if ex.get("inputs"):
        console.print("[bold]Inputs:[/]")
        console.print_json(data=ex["inputs"])
        console.print()

    if ex.get("outputs"):
        console.print("[bold]Outputs:[/]")
        console.print_json(data=ex["outputs"])
        console.print()

    console.print("[bold]Timeline:[/]")
    console.print(f"  Created:   {format_timestamp(ex.get('created_at'))}")
    console.print(f"  Started:   {format_timestamp(ex.get('started_at'))}")
    console.print(f"  Completed: {format_timestamp(ex.get('completed_at'))}")
    console.print()


# ── cancel / pause / resume execution ────────────────────────────────

@workflows_group.command(name="cancel")
@click.argument("execution_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
@require_server
def cancel_execution(execution_id: str, yes: bool) -> None:
    """Cancel a running workflow execution."""
    if not yes and not prompt_confirm(f"Cancel execution {execution_id}?"):
        return

    client = get_client()
    try:
        client.post(f"/api/v1/workflow/executions/{execution_id}/cancel")
        print_success(f"Execution {execution_id} cancelled.")
    except CLIHttpError as e:
        print_error(f"Cancel failed: {e}")


@workflows_group.command(name="pause-exec")
@click.argument("execution_id")
@require_server
def pause_execution(execution_id: str) -> None:
    """Pause a running workflow execution."""
    client = get_client()
    try:
        client.post(f"/api/v1/workflow/executions/{execution_id}/pause")
        print_success(f"Execution {execution_id} paused.")
    except CLIHttpError as e:
        print_error(f"Pause failed: {e}")


@workflows_group.command(name="resume-exec")
@click.argument("execution_id")
@require_server
def resume_execution(execution_id: str) -> None:
    """Resume a paused workflow execution."""
    client = get_client()
    try:
        client.post(f"/api/v1/workflow/executions/{execution_id}/resume")
        print_success(f"Execution {execution_id} resumed.")
    except CLIHttpError as e:
        print_error(f"Resume failed: {e}")
