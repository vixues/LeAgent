"""CLI commands for an optional background ``leagent`` daemon (PID + log files under ``LEAGENT_HOME``)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import click

from leagent.cli.utils import (
    console,
    format_bytes,
    format_duration,
    print_dim,
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
    status_badge,
)
from leagent.config.constants import LOG_DIR, LEAGENT_HOME


PID_FILE = LEAGENT_HOME / "leagent.pid"
DAEMON_LOG = LOG_DIR / "daemon.log"


def _get_pid() -> int | None:
    """Get the PID of the running daemon."""
    if not PID_FILE.exists():
        return None

    try:
        with open(PID_FILE, encoding="utf-8") as f:
            pid = int(f.read().strip())

        if _is_process_running(pid):
            return pid
        else:
            PID_FILE.unlink(missing_ok=True)
            return None
    except (ValueError, IOError):
        return None


def _is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _get_process_info(pid: int) -> dict[str, Any]:
    """Get information about a running process."""
    info: dict[str, Any] = {"pid": pid, "running": False}

    try:
        import psutil

        proc = psutil.Process(pid)
        info["running"] = proc.is_running()
        info["status"] = proc.status()
        info["cpu_percent"] = proc.cpu_percent(interval=0.1)
        info["memory_info"] = proc.memory_info()
        info["memory_percent"] = proc.memory_percent()
        info["create_time"] = proc.create_time()
        info["num_threads"] = proc.num_threads()
        info["cmdline"] = proc.cmdline()

        try:
            info["connections"] = len(proc.connections())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            info["connections"] = None

    except ImportError:
        if _is_process_running(pid):
            info["running"] = True
            info["status"] = "running"
    except Exception:
        pass

    return info


@click.group(name="daemon")
def daemon_group() -> None:
    """Optional background ``leagent`` process tracked via ``LEAGENT_HOME/leagent.pid``."""


@daemon_group.command(name="status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def daemon_status(as_json: bool) -> None:
    """Show the status of the LeAgent daemon."""
    pid = _get_pid()

    if as_json:
        if pid:
            info = _get_process_info(pid)
            console.print_json(data=info)
        else:
            console.print_json(data={"running": False, "pid": None})
        return

    console.print()
    console.rule("[bold cyan]LeAgent Daemon Status[/]")
    console.print()

    if not pid:
        console.print(f"  [bold]Status:[/] {status_badge('stopped')}")
        console.print(f"  [bold]PID File:[/] {PID_FILE}")
        console.print()
        print_info("Daemon is not running. Start it with: leagent daemon start")
        return

    info = _get_process_info(pid)

    console.print(f"  [bold]Status:[/] {status_badge('running' if info.get('running') else 'stopped')}")
    console.print(f"  [bold]PID:[/] {pid}")

    if info.get("create_time"):
        import datetime

        start_time = datetime.datetime.fromtimestamp(info["create_time"])
        uptime = datetime.datetime.now() - start_time
        console.print(f"  [bold]Started:[/] {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        console.print(f"  [bold]Uptime:[/] {format_duration(uptime)}")

    if info.get("cpu_percent") is not None:
        console.print(f"  [bold]CPU:[/] {info['cpu_percent']:.1f}%")

    if info.get("memory_info"):
        mem = info["memory_info"]
        console.print(f"  [bold]Memory:[/] {format_bytes(mem.rss)} ({info.get('memory_percent', 0):.1f}%)")

    if info.get("num_threads"):
        console.print(f"  [bold]Threads:[/] {info['num_threads']}")

    if info.get("connections") is not None:
        console.print(f"  [bold]Connections:[/] {info['connections']}")

    console.print()
    console.print(f"  [dim]Log file:[/] {DAEMON_LOG}")
    console.print(f"  [dim]PID file:[/] {PID_FILE}")
    console.print()


@daemon_group.command(name="start")
@click.option("--host", "-h", default="0.0.0.0", help="Host address to bind to.")
@click.option("--port", "-p", default=7860, type=int, help="Port to bind to.")
@click.option("--workers", "-w", default=None, type=int, help="Number of workers.")
@click.option("--log-level", "-l", default="info", help="Logging level.")
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground instead of daemon.")
def daemon_start(
    host: str,
    port: int,
    workers: int | None,
    log_level: str,
    foreground: bool,
) -> None:
    """Start the LeAgent daemon."""
    pid = _get_pid()

    if pid:
        print_warning(f"Daemon is already running (PID: {pid})")
        print_info("Use 'leagent daemon restart' to restart.")
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LEAGENT_HOME.mkdir(parents=True, exist_ok=True)

    if foreground:
        console.print(f"Starting LeAgent in foreground on {host}:{port}...")
        _run_server(host, port, workers, log_level)
        return

    console.print(f"Starting LeAgent daemon on {host}:{port}...")

    try:
        cmd = [
            sys.executable, "-m", "leagent.cli.main",
            "app", "start",
            "--host", host,
            "--port", str(port),
            "--log-level", log_level,
        ]

        if workers:
            cmd.extend(["--workers", str(workers)])

        log_file = open(DAEMON_LOG, "a", encoding="utf-8")

        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            cwd=str(LEAGENT_HOME),
        )

        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(process.pid))

        time.sleep(1)

        if _is_process_running(process.pid):
            print_success(f"Daemon started (PID: {process.pid})")
            console.print(f"  [dim]Log file:[/] {DAEMON_LOG}")
        else:
            print_error("Daemon failed to start. Check logs for details.")
            print_dim(f"Log file: {DAEMON_LOG}")

    except Exception as e:
        print_error(f"Failed to start daemon: {e}")
        raise click.Abort()


def _run_server(host: str, port: int, workers: int | None, log_level: str) -> None:
    """Run the server directly (not as daemon)."""
    from leagent.server import run_uvicorn

    run_uvicorn(host=host, port=port, workers=workers or 1, log_level=log_level)


@daemon_group.command(name="stop")
@click.option("--force", "-f", is_flag=True, help="Force kill the daemon.")
@click.option("--timeout", "-t", default=10, type=int, help="Timeout for graceful shutdown.")
def daemon_stop(force: bool, timeout: int) -> None:
    """Stop the LeAgent daemon."""
    pid = _get_pid()

    if not pid:
        print_info("Daemon is not running.")
        return

    console.print(f"Stopping daemon (PID: {pid})...")

    try:
        if force:
            os.kill(pid, signal.SIGKILL)
            print_success("Daemon killed.")
        else:
            os.kill(pid, signal.SIGTERM)

            for i in range(timeout):
                time.sleep(1)
                if not _is_process_running(pid):
                    print_success("Daemon stopped gracefully.")
                    break
            else:
                print_warning("Graceful shutdown timed out. Forcing...")
                os.kill(pid, signal.SIGKILL)
                print_success("Daemon killed.")

    except ProcessLookupError:
        print_info("Daemon was already stopped.")
    except Exception as e:
        print_error(f"Failed to stop daemon: {e}")
        raise click.Abort()
    finally:
        PID_FILE.unlink(missing_ok=True)


@daemon_group.command(name="restart")
@click.option("--host", "-h", default="0.0.0.0", help="Host address to bind to.")
@click.option("--port", "-p", default=7860, type=int, help="Port to bind to.")
@click.option("--workers", "-w", default=None, type=int, help="Number of workers.")
@click.option("--log-level", "-l", default="info", help="Logging level.")
def daemon_restart(host: str, port: int, workers: int | None, log_level: str) -> None:
    """Restart the LeAgent daemon."""
    pid = _get_pid()

    if pid:
        console.print(f"Stopping daemon (PID: {pid})...")

        try:
            os.kill(pid, signal.SIGTERM)

            for _ in range(10):
                time.sleep(1)
                if not _is_process_running(pid):
                    break
            else:
                os.kill(pid, signal.SIGKILL)

        except ProcessLookupError:
            pass
        finally:
            PID_FILE.unlink(missing_ok=True)

        print_success("Daemon stopped.")
        time.sleep(1)

    ctx = click.get_current_context()
    ctx.invoke(daemon_start, host=host, port=port, workers=workers, log_level=log_level)


@daemon_group.command(name="logs")
@click.option("--lines", "-n", default=50, type=int, help="Number of lines to show.")
@click.option("--follow", "-f", is_flag=True, help="Follow log output.")
@click.option("--level", "-l", default=None, help="Filter by log level.")
def daemon_logs(lines: int, follow: bool, level: str | None) -> None:
    """Show daemon logs."""
    if not DAEMON_LOG.exists():
        print_info("No daemon logs found.")
        print_dim(f"Expected location: {DAEMON_LOG}")
        return

    console.print(f"[dim]Log file: {DAEMON_LOG}[/]\n")

    if follow:
        try:
            process = subprocess.Popen(
                ["tail", "-f", "-n", str(lines), str(DAEMON_LOG)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            try:
                while True:
                    line = process.stdout.readline()
                    if not line:
                        break

                    if level:
                        level_upper = level.upper()
                        if level_upper in line.upper():
                            _print_log_line(line.rstrip())
                    else:
                        _print_log_line(line.rstrip())

            except KeyboardInterrupt:
                process.terminate()

        except FileNotFoundError:
            with open(DAEMON_LOG, encoding="utf-8", errors="replace") as f:
                content = f.readlines()

            for line in content[-lines:]:
                if level:
                    if level.upper() in line.upper():
                        _print_log_line(line.rstrip())
                else:
                    _print_log_line(line.rstrip())

            print_info("Follow mode not available. Showing last entries.")

    else:
        with open(DAEMON_LOG, encoding="utf-8", errors="replace") as f:
            content = f.readlines()

        for line in content[-lines:]:
            if level:
                if level.upper() in line.upper():
                    _print_log_line(line.rstrip())
            else:
                _print_log_line(line.rstrip())


def _print_log_line(line: str) -> None:
    """Print a log line with color based on level."""
    if "ERROR" in line.upper():
        console.print(f"[red]{line}[/]")
    elif "WARNING" in line.upper() or "WARN" in line.upper():
        console.print(f"[yellow]{line}[/]")
    elif "INFO" in line.upper():
        console.print(line)
    elif "DEBUG" in line.upper():
        console.print(f"[dim]{line}[/]")
    else:
        console.print(line)


@daemon_group.command(name="reload")
def daemon_reload() -> None:
    """Reload daemon configuration without restart."""
    pid = _get_pid()

    if not pid:
        print_error("Daemon is not running.")
        raise click.Abort()

    console.print(f"Sending reload signal to daemon (PID: {pid})...")

    try:
        os.kill(pid, signal.SIGHUP)
        print_success("Reload signal sent. Daemon will reload configuration.")
    except Exception as e:
        print_error(f"Failed to send reload signal: {e}")
        raise click.Abort()
