"""CLI commands for scheduled jobs (workflow engine + APScheduler hooks).

Server mode uses ``/api/v1/cron``; offline edits use YAML under ``JOBS_PATH`` / ``LEAGENT_HOME``.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import click
import yaml

from leagent.cli.http import CLIHttpError, get_client
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
    prompt_text,
    status_badge,
    truncate_text,
)
from leagent.config.constants import JOBS_PATH, LOG_DIR


# ── Helpers ──────────────────────────────────────────────────────────

def _server_available() -> bool:
    try:
        client = get_client()
        return client.health_check()
    except Exception:
        return False


def _validate_cron_expression(expr: str) -> bool:
    try:
        from croniter import croniter
        croniter(expr)
        return True
    except Exception:
        parts = expr.split()
        return len(parts) == 5


def _get_next_runs(cron_expr: str, count: int = 1) -> list[datetime]:
    try:
        from croniter import croniter
        cron = croniter(cron_expr, datetime.now())
        return [cron.get_next(datetime) for _ in range(count)]
    except Exception:
        return []


# ── Local YAML fallback ─────────────────────────────────────────────

def _get_jobs_file() -> Path:
    return JOBS_PATH / "cron_jobs.yaml"


def _load_local_jobs() -> list[dict[str, Any]]:
    jobs_file = _get_jobs_file()
    if not jobs_file.exists():
        return []
    with open(jobs_file, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
        return data.get("jobs", [])


def _save_local_jobs(jobs: list[dict[str, Any]]) -> None:
    jobs_file = _get_jobs_file()
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    with open(jobs_file, "w", encoding="utf-8") as f:
        yaml.dump(
            {"jobs": jobs},
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


def _find_local_job(jobs: list[dict[str, Any]], name_or_id: str) -> dict[str, Any] | None:
    for job in jobs:
        if job.get("name") == name_or_id or job.get("id", "").startswith(name_or_id):
            return job
    return None


# ── Click group ──────────────────────────────────────────────────────

@click.group(name="cron")
def cron_group() -> None:
    """Scheduled jobs: ``/api/v1/cron`` when the monolith is up, else local YAML under ``JOBS_PATH``."""


# ── list ─────────────────────────────────────────────────────────────

@cron_group.command(name="list")
@click.option("--all", "-a", "show_all", is_flag=True, help="Show all jobs including paused.")
@click.option("--status", "-s", "filter_status", default=None, help="Filter by status.")
@click.option("--type", "-t", "filter_type", default=None, help="Filter by target type (flow/task/webhook/script).")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def list_jobs(show_all: bool, filter_status: str | None, filter_type: str | None, as_json: bool) -> None:
    """List all configured cron jobs."""
    if _server_available():
        try:
            client = get_client()
            params: dict[str, Any] = {}
            if filter_status:
                params["status"] = filter_status
            if filter_type:
                params["target_type"] = filter_type
            result = client.get("/api/v1/cron", params=params)
            jobs = result.get("items", result.get("jobs", []))
        except CLIHttpError as e:
            print_warning(f"API error: {e}")
            jobs = _load_local_jobs()
    else:
        jobs = _load_local_jobs()

    if as_json:
        console.print_json(data=jobs)
        return

    if not jobs:
        print_info("No cron jobs configured.")
        print_dim("Add a job with: leagent cron add --name <name> --schedule '<cron>' --target <id>")
        return

    console.print()
    console.rule("[bold cyan]Cron Jobs[/]")
    console.print()

    table = create_table(
        columns=[
            ("ID", {"style": "dim"}),
            ("Name", {"style": "cyan"}),
            ("Schedule", {}),
            ("Type", {}),
            ("Status", {}),
            ("Last Run", {}),
            ("Next Run", {}),
        ],
    )

    for job in jobs:
        status = job.get("status", "active")
        if not show_all and status in ("paused", "disabled"):
            continue

        job_id = str(job.get("id", "-"))[:8]
        name = job.get("name", "-")
        schedule = job.get("schedule", "-")
        target_type = job.get("target_type", job.get("type", "-"))
        last_run = format_timestamp(job.get("last_run_at", job.get("last_run")))
        next_run = job.get("next_run_at")
        if not next_run:
            runs = _get_next_runs(schedule)
            next_run = runs[0] if runs else None
        next_run_str = format_timestamp(next_run) if next_run else "-"

        table.add_row(job_id, name, schedule, target_type, status_badge(status), last_run, next_run_str)

    console.print(table)
    console.print()


# ── add ──────────────────────────────────────────────────────────────

@cron_group.command(name="add")
@click.option("--name", "-n", required=True, help="Job name.")
@click.option("--schedule", "-s", required=True, help="Cron schedule expression (e.g., '0 9 * * 1-5').")
@click.option("--target-type", "-t", type=click.Choice(["flow", "task", "webhook", "script"]), default="flow", help="Target type.")
@click.option("--target-id", required=False, default=None, help="Target ID (flow/workflow UUID).")
@click.option("--workflow-id", "-w", default=None, help="Workflow ID to execute (alias for flow target).")
@click.option("--description", "-d", default="", help="Job description.")
@click.option("--payload", "-p", default=None, help="JSON payload string.")
@click.option("--timezone", default=None, help="Timezone for schedule (e.g., Asia/Shanghai).")
@click.option("--timeout", default=300, type=int, help="Execution timeout in seconds.")
@click.option("--max-retries", default=0, type=int, help="Max retry count on failure.")
@click.option("--notify-on-fail/--no-notify-on-fail", default=False, help="Send notification on failure.")
@click.option("--notify-on-complete/--no-notify-on-complete", default=False, help="Send notification on completion.")
@click.option("--channel-ids", default=None, help="Comma-separated notification channel IDs.")
@click.option("--enabled/--disabled", default=True, help="Enable the job immediately.")
@click.option("--tags", default=None, help="Comma-separated tags.")
def add_job(
    name: str,
    schedule: str,
    target_type: str,
    target_id: str | None,
    workflow_id: str | None,
    description: str,
    payload: str | None,
    timezone: str | None,
    timeout: int,
    max_retries: int,
    notify_on_fail: bool,
    notify_on_complete: bool,
    channel_ids: str | None,
    enabled: bool,
    tags: str | None,
) -> None:
    """Add a new cron job."""
    if not _validate_cron_expression(schedule):
        print_error(f"Invalid cron expression: {schedule}")
        print_info("Format: minute hour day month weekday")
        print_info("Example: '0 9 * * 1-5' (9 AM weekdays)")
        raise click.Abort()

    parsed_payload = None
    if payload:
        try:
            parsed_payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            print_error(f"Invalid JSON payload: {exc}")
            raise click.Abort()

    effective_target_id = target_id or workflow_id
    effective_workflow_id = workflow_id

    if _server_available():
        try:
            client = get_client()
            body: dict[str, Any] = {
                "name": name,
                "description": description,
                "schedule": schedule,
                "target_type": target_type,
                "enabled": enabled,
                "timeout_sec": timeout,
                "max_retries": max_retries,
                "notify_on_fail": notify_on_fail,
                "notify_on_complete": notify_on_complete,
            }
            if effective_target_id:
                body["target_id"] = effective_target_id
            if effective_workflow_id:
                body["workflow_id"] = effective_workflow_id
            if parsed_payload:
                body["payload"] = parsed_payload
            if timezone:
                body["timezone"] = timezone
            if channel_ids:
                body["channel_ids"] = [c.strip() for c in channel_ids.split(",")]
            if tags:
                body["tags"] = [t.strip() for t in tags.split(",")]

            result = client.post("/api/v1/cron", json=body)
            job_id = result.get("id", "unknown")
            print_success(f"Job '{name}' created via API.")
            console.print(f"  [dim]ID:[/] {job_id}")
            console.print(f"  [dim]Schedule:[/] {schedule}")
            if result.get("next_run_at"):
                console.print(f"  [dim]Next run:[/] {format_timestamp(result['next_run_at'])}")
            return

        except CLIHttpError as e:
            print_warning(f"API error: {e}. Falling back to local storage.")

    jobs = _load_local_jobs()
    for job in jobs:
        if job.get("name") == name:
            print_error(f"Job with name '{name}' already exists.")
            raise click.Abort()

    job_id = str(uuid.uuid4())
    new_job: dict[str, Any] = {
        "id": job_id,
        "name": name,
        "description": description,
        "schedule": schedule,
        "target_type": target_type,
        "target_id": effective_target_id,
        "workflow_id": effective_workflow_id,
        "status": "active" if enabled else "paused",
        "timeout_sec": timeout,
        "max_retries": max_retries,
        "notify_on_fail": notify_on_fail,
        "notify_on_complete": notify_on_complete,
        "tags": [t.strip() for t in tags.split(",")] if tags else [],
        "created_at": datetime.now().isoformat(),
        "last_run_at": None,
        "run_count": 0,
    }
    if parsed_payload:
        new_job["payload"] = parsed_payload
    if timezone:
        new_job["timezone"] = timezone
    if channel_ids:
        new_job["channel_ids"] = [c.strip() for c in channel_ids.split(",")]

    jobs.append(new_job)
    _save_local_jobs(jobs)

    print_success(f"Job '{name}' created (local).")
    console.print(f"  [dim]ID:[/] {job_id}")
    console.print(f"  [dim]Schedule:[/] {schedule}")
    runs = _get_next_runs(schedule)
    if runs:
        console.print(f"  [dim]Next run:[/] {format_timestamp(runs[0])}")


# ── show ─────────────────────────────────────────────────────────────

@cron_group.command(name="show")
@click.argument("name_or_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def show_job(name_or_id: str, as_json: bool) -> None:
    """Show detailed information about a cron job."""
    job = _fetch_job(name_or_id)

    if as_json:
        console.print_json(data=job)
        return

    console.print()
    console.rule(f"[bold cyan]Job: {job.get('name')}[/]")
    console.print()

    console.print(f"  [bold]ID:[/]           {job.get('id')}")
    console.print(f"  [bold]Name:[/]         {job.get('name')}")
    console.print(f"  [bold]Description:[/]  {job.get('description') or '-'}")
    console.print(f"  [bold]Schedule:[/]     {job.get('schedule')}")
    console.print(f"  [bold]Target type:[/]  {job.get('target_type', '-')}")
    console.print(f"  [bold]Target ID:[/]    {job.get('target_id') or '-'}")
    console.print(f"  [bold]Workflow ID:[/]  {job.get('workflow_id') or '-'}")
    console.print(f"  [bold]Status:[/]       {status_badge(job.get('status', 'active'))}")
    console.print(f"  [bold]Timezone:[/]     {job.get('timezone') or 'UTC'}")
    console.print()

    console.print("[bold]Execution Settings:[/]")
    console.print(f"  Timeout:       {job.get('timeout_sec', 300)}s")
    console.print(f"  Max retries:   {job.get('max_retries', 0)}")
    console.print(f"  Max instances: {job.get('max_instances', 1)}")
    console.print()

    console.print("[bold]Notifications:[/]")
    console.print(f"  On start:    {job.get('notify_on_start', False)}")
    console.print(f"  On complete: {job.get('notify_on_complete', False)}")
    console.print(f"  On fail:     {job.get('notify_on_fail', False)}")
    channels = job.get("channel_ids", [])
    console.print(f"  Channels:    {', '.join(str(c) for c in channels) if channels else '-'}")
    console.print()

    console.print("[bold]Statistics:[/]")
    console.print(f"  Run count:     {job.get('run_count', job.get('success_count', 0) + job.get('failure_count', 0))}")
    console.print(f"  Successes:     {job.get('success_count', '-')}")
    console.print(f"  Failures:      {job.get('failure_count', '-')}")
    console.print(f"  Consecutive:   {job.get('consecutive_failures', '-')}")
    console.print(f"  Last run:      {format_timestamp(job.get('last_run_at', job.get('last_run')))}")
    console.print(f"  Last status:   {job.get('last_run_status', '-')}")
    console.print(f"  Last error:    {truncate_text(str(job.get('last_error', '-')), 80)}")

    next_run = job.get("next_run_at")
    if not next_run:
        runs = _get_next_runs(job.get("schedule", ""))
        next_run = runs[0] if runs else None
    console.print(f"  Next run:      {format_timestamp(next_run) if next_run else '-'}")
    console.print()

    console.print("[bold]Metadata:[/]")
    console.print(f"  Created:  {format_timestamp(job.get('created_at'))}")
    console.print(f"  Updated:  {format_timestamp(job.get('updated_at'))}")
    console.print(f"  Tags:     {', '.join(job.get('tags', [])) or '-'}")
    console.print(f"  Version:  {job.get('version', '-')}")
    console.print()


def _fetch_job(name_or_id: str) -> dict[str, Any]:
    """Fetch a job from the server API, falling back to local."""
    if _server_available():
        try:
            client = get_client()
            return client.get(f"/api/v1/cron/{name_or_id}")
        except CLIHttpError:
            pass

    jobs = _load_local_jobs()
    job = _find_local_job(jobs, name_or_id)
    if not job:
        print_error(f"Job '{name_or_id}' not found.")
        raise click.Abort()
    return job


# ── remove ───────────────────────────────────────────────────────────

@cron_group.command(name="remove")
@click.argument("name_or_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def remove_job(name_or_id: str, yes: bool) -> None:
    """Remove a cron job."""
    if not yes:
        if not prompt_confirm(f"Remove job '{name_or_id}'?"):
            print_info("Cancelled.")
            return

    if _server_available():
        try:
            client = get_client()
            client.delete(f"/api/v1/cron/{name_or_id}")
            print_success(f"Job '{name_or_id}' removed.")
            return
        except CLIHttpError as e:
            print_warning(f"API error: {e}. Trying local storage.")

    jobs = _load_local_jobs()
    job = _find_local_job(jobs, name_or_id)
    if not job:
        print_error(f"Job '{name_or_id}' not found.")
        raise click.Abort()

    jobs.remove(job)
    _save_local_jobs(jobs)
    print_success(f"Job '{job.get('name')}' removed.")


# ── pause / resume ───────────────────────────────────────────────────

@cron_group.command(name="pause")
@click.argument("name_or_id")
def pause_job(name_or_id: str) -> None:
    """Pause a cron job."""
    if _server_available():
        try:
            client = get_client()
            client.post(f"/api/v1/cron/{name_or_id}/pause")
            print_success(f"Job '{name_or_id}' paused.")
            return
        except CLIHttpError as e:
            print_warning(f"API error: {e}. Trying local storage.")

    jobs = _load_local_jobs()
    job = _find_local_job(jobs, name_or_id)
    if not job:
        print_error(f"Job '{name_or_id}' not found.")
        raise click.Abort()
    if job.get("status") == "paused":
        print_info(f"Job '{job.get('name')}' is already paused.")
        return
    job["status"] = "paused"
    _save_local_jobs(jobs)
    print_success(f"Job '{job.get('name')}' paused.")


@cron_group.command(name="resume")
@click.argument("name_or_id")
def resume_job(name_or_id: str) -> None:
    """Resume a paused cron job."""
    if _server_available():
        try:
            client = get_client()
            client.post(f"/api/v1/cron/{name_or_id}/resume")
            print_success(f"Job '{name_or_id}' resumed.")
            return
        except CLIHttpError as e:
            print_warning(f"API error: {e}. Trying local storage.")

    jobs = _load_local_jobs()
    job = _find_local_job(jobs, name_or_id)
    if not job:
        print_error(f"Job '{name_or_id}' not found.")
        raise click.Abort()
    if job.get("status") == "active":
        print_info(f"Job '{job.get('name')}' is already active.")
        return
    job["status"] = "active"
    _save_local_jobs(jobs)
    print_success(f"Job '{job.get('name')}' resumed.")


# ── run (trigger immediately) ────────────────────────────────────────

@cron_group.command(name="run")
@click.argument("name_or_id")
@click.option("--input", "-i", "input_json", default=None, help="JSON input override.")
@click.option("--wait/--no-wait", default=False, help="Wait for execution to complete.")
def run_job(name_or_id: str, input_json: str | None, wait: bool) -> None:
    """Manually trigger a cron job to run immediately."""
    inputs = None
    if input_json:
        try:
            inputs = json.loads(input_json)
        except json.JSONDecodeError as exc:
            print_error(f"Invalid JSON: {exc}")
            raise click.Abort()

    if _server_available():
        try:
            client = get_client()
            body: dict[str, Any] = {}
            if inputs:
                body["inputs"] = inputs
            result = client.post(f"/api/v1/cron/{name_or_id}/run", json=body)
            exec_id = result.get("execution_id", result.get("id", "unknown"))
            print_success(f"Job triggered. Execution ID: {exec_id}")

            if wait and exec_id != "unknown":
                _poll_execution(name_or_id, exec_id)
            return

        except CLIHttpError as e:
            print_warning(f"API error: {e}. Cannot trigger remotely.")
            return

    print_error("Server not running. Cannot trigger job execution without server.")
    print_info("Start the server with: leagent app start")


def _poll_execution(job_id: str, execution_id: str) -> None:
    """Poll execution status until terminal."""
    import time

    client = get_client()
    terminal_states = {"completed", "failed", "cancelled", "timeout", "skipped"}

    console.print("[dim]Waiting for execution to complete...[/]")
    for _ in range(120):
        try:
            result = client.get(f"/api/v1/cron/{job_id}/history", params={"limit": 5})
            executions = result.get("items", result.get("executions", []))
            for ex in executions:
                if str(ex.get("id", "")).startswith(execution_id) or str(ex.get("execution_number", "")) == execution_id:
                    st = ex.get("status", "")
                    if st in terminal_states:
                        if st == "completed":
                            print_success(f"Execution completed in {ex.get('duration_ms', '?')}ms")
                        else:
                            print_error(f"Execution {st}: {ex.get('error', '-')}")
                        return
        except CLIHttpError:
            pass
        time.sleep(2)

    print_warning("Timed out waiting for execution. Check status with: leagent cron history")


# ── clone ────────────────────────────────────────────────────────────

@cron_group.command(name="clone")
@click.argument("name_or_id")
@click.option("--new-name", required=True, help="Name for the cloned job.")
def clone_job(name_or_id: str, new_name: str) -> None:
    """Clone an existing cron job with a new name."""
    if _server_available():
        try:
            client = get_client()
            result = client.post(
                f"/api/v1/cron/{name_or_id}/clone",
                json={"name": new_name},
            )
            print_success(f"Job cloned as '{new_name}'.")
            console.print(f"  [dim]ID:[/] {result.get('id', 'unknown')}")
            return
        except CLIHttpError as e:
            print_warning(f"API error: {e}. Trying local clone.")

    jobs = _load_local_jobs()
    job = _find_local_job(jobs, name_or_id)
    if not job:
        print_error(f"Job '{name_or_id}' not found.")
        raise click.Abort()

    if _find_local_job(jobs, new_name):
        print_error(f"Job with name '{new_name}' already exists.")
        raise click.Abort()

    cloned = dict(job)
    cloned["id"] = str(uuid.uuid4())
    cloned["name"] = new_name
    cloned["status"] = "paused"
    cloned["last_run_at"] = None
    cloned["last_run"] = None
    cloned["run_count"] = 0
    cloned["created_at"] = datetime.now().isoformat()
    jobs.append(cloned)
    _save_local_jobs(jobs)
    print_success(f"Job cloned as '{new_name}' (local, paused).")


# ── history ──────────────────────────────────────────────────────────

@cron_group.command(name="history")
@click.argument("name_or_id", required=False)
@click.option("--limit", "-n", default=20, type=int, help="Number of executions to show.")
@click.option("--status", "-s", "filter_status", default=None, help="Filter by execution status.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def show_history(
    name_or_id: str | None,
    limit: int,
    filter_status: str | None,
    as_json: bool,
) -> None:
    """Show cron job execution history."""
    if not _server_available():
        print_error("Server not running. Execution history requires the server API.")
        print_info("Start the server with: leagent app start")
        _show_local_logs(name_or_id, limit)
        return

    try:
        client = get_client()
        params: dict[str, Any] = {"limit": limit}
        if filter_status:
            params["status"] = filter_status

        if name_or_id:
            result = client.get(f"/api/v1/cron/{name_or_id}/history", params=params)
        else:
            result = client.get("/api/v1/cron/history", params=params)

        executions = result.get("items", result.get("executions", []))

    except CLIHttpError as e:
        print_error(f"Failed to fetch history: {e}")
        raise click.Abort()

    if as_json:
        console.print_json(data=executions)
        return

    if not executions:
        print_info("No execution history found.")
        return

    console.print()
    title = f"Execution History: {name_or_id}" if name_or_id else "Recent Executions"
    console.rule(f"[bold cyan]{title}[/]")
    console.print()

    table = create_table(
        columns=[
            ("Execution", {"style": "dim"}),
            ("Job", {"style": "cyan"}),
            ("Status", {}),
            ("Trigger", {}),
            ("Started", {}),
            ("Duration", {"justify": "right"}),
            ("Error", {}),
        ],
    )

    for ex in executions:
        exec_id = str(ex.get("id", "-"))[:8]
        job_name = ex.get("job_name", "-")
        st = ex.get("status", "-")
        trigger = ex.get("trigger_type", "-")
        started = format_timestamp(ex.get("started_at"))
        duration = f"{ex.get('duration_ms', 0)}ms" if ex.get("duration_ms") else "-"
        error = truncate_text(str(ex.get("error", "") or ""), 30)

        table.add_row(exec_id, job_name, status_badge(st), trigger, started, duration, error)

    console.print(table)
    console.print()


def _show_local_logs(name_or_id: str | None, limit: int) -> None:
    """Show local cron logs as fallback."""
    cron_log_dir = LOG_DIR / "cron"
    if not cron_log_dir.exists():
        return

    log_files = sorted(cron_log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not log_files:
        return

    print_info("Showing local log files instead:")
    for lf in log_files[:limit]:
        mtime = format_timestamp(datetime.fromtimestamp(lf.stat().st_mtime))
        console.print(f"  [dim]{lf.stem[:8]}[/]  {mtime}  {lf.stat().st_size:,} bytes")


# ── stats ────────────────────────────────────────────────────────────

@cron_group.command(name="stats")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def show_stats(as_json: bool) -> None:
    """Show cron system statistics."""
    if not _server_available():
        print_error("Server not running. Stats require the server API.")
        return

    try:
        client = get_client()
        stats = client.get("/api/v1/cron/stats")
    except CLIHttpError as e:
        print_error(f"Failed to fetch stats: {e}")
        raise click.Abort()

    if as_json:
        console.print_json(data=stats)
        return

    console.print()
    console.rule("[bold cyan]Cron Statistics[/]")
    console.print()
    console.print(f"  [bold]Total jobs:[/]         {stats.get('total_jobs', 0)}")
    console.print(f"  [bold]Active jobs:[/]        {stats.get('active_jobs', 0)}")
    console.print(f"  [bold]Paused jobs:[/]        {stats.get('paused_jobs', 0)}")
    console.print(f"  [bold]Total executions:[/]   {stats.get('total_executions', 0)}")
    console.print(f"  [bold]Recent successes:[/]   {stats.get('recent_successes', 0)}")
    console.print(f"  [bold]Recent failures:[/]    {stats.get('recent_failures', 0)}")
    console.print(f"  [bold]Scheduler running:[/]  {stats.get('scheduler_running', False)}")
    console.print()


# ── next-runs ────────────────────────────────────────────────────────

@cron_group.command(name="next-runs")
@click.argument("name_or_id", required=False)
@click.option("--count", "-n", default=5, type=int, help="Number of upcoming runs to show.")
def next_runs(name_or_id: str | None, count: int) -> None:
    """Preview upcoming scheduled run times."""
    if name_or_id and _server_available():
        try:
            client = get_client()
            result = client.get(f"/api/v1/cron/{name_or_id}/next-runs", params={"count": count})
            runs = result.get("runs", [])
            console.print()
            console.print(f"[bold cyan]Next {count} runs for {name_or_id}:[/]")
            for i, run_time in enumerate(runs, 1):
                console.print(f"  {i}. {format_timestamp(run_time)}")
            console.print()
            return
        except CLIHttpError:
            pass

    if name_or_id:
        job = _fetch_job(name_or_id)
        schedule = job.get("schedule", "")
    else:
        schedule = prompt_text("Enter cron expression")

    if not schedule:
        print_error("No schedule provided.")
        return

    if not _validate_cron_expression(schedule):
        print_error(f"Invalid cron expression: {schedule}")
        return

    runs = _get_next_runs(schedule, count)
    if not runs:
        print_error("Could not compute next runs. Is croniter installed?")
        return

    console.print()
    console.print(f"[bold cyan]Next {count} runs ({schedule}):[/]")
    for i, run_time in enumerate(runs, 1):
        console.print(f"  {i}. {format_timestamp(run_time)}")
    console.print()


# ── health ───────────────────────────────────────────────────────────

@cron_group.command(name="health")
def cron_health() -> None:
    """Check cron scheduler health."""
    if not _server_available():
        print_warning("Server not running.")
        print_dim("Local jobs will not execute without the server.")
        return

    try:
        client = get_client()
        result = client.get("/api/v1/cron/health")

        running = result.get("scheduler_running", result.get("running", False))
        job_count = result.get("job_count", 0)
        pending = result.get("pending_jobs", 0)

        if running:
            print_success(f"Cron scheduler is healthy ({job_count} jobs, {pending} pending)")
        else:
            print_error("Cron scheduler is not running")

        if result.get("last_heartbeat"):
            console.print(f"  [dim]Last heartbeat:[/] {format_timestamp(result['last_heartbeat'])}")

    except CLIHttpError as e:
        print_error(f"Health check failed: {e}")


# ── logs ─────────────────────────────────────────────────────────────

@cron_group.command(name="logs")
@click.argument("name_or_id", required=False)
@click.option("--lines", "-n", default=50, help="Number of lines to show.")
@click.option("--follow", "-f", is_flag=True, help="Follow log output.")
def show_logs(name_or_id: str | None, lines: int, follow: bool) -> None:
    """Show cron job execution logs."""
    cron_log_dir = LOG_DIR / "cron"

    if not cron_log_dir.exists():
        print_info("No cron logs found.")
        return

    if name_or_id:
        job = None
        try:
            job = _fetch_job(name_or_id)
        except (click.Abort, SystemExit):
            pass

        job_id = job.get("id") if job else name_or_id
        log_file = cron_log_dir / f"{job_id}.log"

        if not log_file.exists():
            log_candidates = list(cron_log_dir.glob(f"{name_or_id}*"))
            if log_candidates:
                log_file = log_candidates[0]
            else:
                print_info(f"No logs found for '{name_or_id}'")
                return

        _show_log_file(log_file, lines, follow)
    else:
        log_files = sorted(cron_log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not log_files:
            print_info("No cron logs found.")
            return

        console.print()
        console.rule("[bold cyan]Recent Cron Logs[/]")
        console.print()

        table = create_table(
            columns=[
                ("Job ID", {"style": "dim"}),
                ("Last Modified", {}),
                ("Size", {"justify": "right"}),
            ],
        )
        for lf in log_files[:10]:
            table.add_row(
                lf.stem[:8],
                format_timestamp(datetime.fromtimestamp(lf.stat().st_mtime)),
                f"{lf.stat().st_size:,} bytes",
            )
        console.print(table)
        console.print()


def _show_log_file(log_file: Path, lines: int, follow: bool) -> None:
    if follow:
        import subprocess
        try:
            subprocess.run(["tail", "-f", "-n", str(lines), str(log_file)])
        except KeyboardInterrupt:
            pass
    else:
        with open(log_file, encoding="utf-8", errors="replace") as f:
            content = f.readlines()
        for line in content[-lines:]:
            console.print(line.rstrip())
