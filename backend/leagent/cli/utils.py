"""CLI utility functions for output formatting, prompts, and helpers."""

from __future__ import annotations

import sys
from datetime import timedelta
from typing import Any, Sequence

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

custom_theme = Theme({
    "success": "bold green",
    "error": "bold red",
    "warning": "bold yellow",
    "info": "bold blue",
    "dim": "dim",
    "highlight": "bold cyan",
})

console = Console(theme=custom_theme)
err_console = Console(stderr=True, theme=custom_theme)


def prompt_confirm(message: str, default: bool = False) -> bool:
    """Prompt the user for a yes/no confirmation."""
    return Confirm.ask(message, default=default, console=console)


def prompt_text(
    message: str,
    default: str = "",
    password: bool = False,
    choices: Sequence[str] | None = None,
) -> str:
    """Prompt the user for text input."""
    return Prompt.ask(
        message,
        default=default or None,
        password=password,
        choices=list(choices) if choices else None,
        console=console,
    )


def prompt_choice(message: str, choices: Sequence[str], default: str | None = None) -> str:
    """Prompt the user to select from a list of choices."""
    return Prompt.ask(
        message,
        choices=list(choices),
        default=default,
        console=console,
    )


def print_success(message: str, prefix: str = "✓") -> None:
    """Print a success message in green."""
    console.print(f"[success]{prefix}[/] {message}")


def print_error(message: str, prefix: str = "✗") -> None:
    """Print an error message in red to stderr."""
    err_console.print(f"[error]{prefix}[/] {message}")


def print_warning(message: str, prefix: str = "⚠") -> None:
    """Print a warning message in yellow."""
    console.print(f"[warning]{prefix}[/] {message}")


def print_info(message: str, prefix: str = "ℹ") -> None:
    """Print an informational message in blue."""
    console.print(f"[info]{prefix}[/] {message}")


def print_dim(message: str) -> None:
    """Print a dimmed/muted message."""
    console.print(f"[dim]{message}[/]")


def print_header(title: str, subtitle: str = "") -> None:
    """Print a styled header."""
    text = Text(title, style="bold cyan")
    if subtitle:
        text.append(f"\n{subtitle}", style="dim")
    console.print(Panel(text, border_style="cyan", padding=(0, 2)))


def print_json(data: Any) -> None:
    """Pretty-print JSON data."""
    console.print_json(data=data)


def create_table(
    title: str | None = None,
    columns: Sequence[str | tuple[str, dict[str, Any]]] | None = None,
    rows: Sequence[Sequence[Any]] | None = None,
    show_header: bool = True,
    show_lines: bool = False,
    box_style: Any = None,
    caption: str | None = None,
) -> Table:
    """Create a rich Table with optional pre-populated data.

    Args:
        title: Table title.
        columns: Column names or tuples of (name, kwargs) for add_column.
        rows: Rows of data to populate.
        show_header: Whether to show the header row.
        show_lines: Whether to show row separator lines.
        box_style: Rich box style to use.
        caption: Table caption.

    Returns:
        A configured Table instance.
    """
    from rich.box import ROUNDED

    table = Table(
        title=title,
        show_header=show_header,
        show_lines=show_lines,
        box=box_style or ROUNDED,
        caption=caption,
        header_style="bold cyan",
        title_style="bold",
    )

    if columns:
        for col in columns:
            if isinstance(col, tuple):
                name, kwargs = col
                table.add_column(name, **kwargs)
            else:
                table.add_column(col)

    if rows:
        for row in rows:
            table.add_row(*[str(cell) if cell is not None else "" for cell in row])

    return table


def create_spinner(text: str = "Loading...") -> Progress:
    """Create a spinner progress indicator."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    )


def format_bytes(num_bytes: int | float, precision: int = 2) -> str:
    """Format a byte count into a human-readable string.

    Args:
        num_bytes: Number of bytes.
        precision: Decimal places to show.

    Returns:
        Formatted string like '1.5 GB'.
    """
    if num_bytes < 0:
        return f"-{format_bytes(-num_bytes, precision)}"

    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.{precision}f} {unit}"
        num_bytes /= 1024.0

    return f"{num_bytes:.{precision}f} EB"


def format_duration(
    seconds: float | int | timedelta,
    short: bool = False,
) -> str:
    """Format a duration into a human-readable string.

    Args:
        seconds: Duration in seconds or a timedelta.
        short: If True, use abbreviated units (1h 30m vs 1 hour 30 minutes).

    Returns:
        Formatted duration string.
    """
    if isinstance(seconds, timedelta):
        seconds = seconds.total_seconds()

    seconds = int(seconds)

    if seconds < 0:
        return f"-{format_duration(-seconds, short)}"

    if seconds == 0:
        return "0s" if short else "0 seconds"

    parts = []
    units = [
        (86400, "d", "day"),
        (3600, "h", "hour"),
        (60, "m", "minute"),
        (1, "s", "second"),
    ]

    for divisor, short_unit, long_unit in units:
        if seconds >= divisor:
            value = seconds // divisor
            seconds %= divisor
            if short:
                parts.append(f"{value}{short_unit}")
            else:
                unit_str = long_unit if value == 1 else f"{long_unit}s"
                parts.append(f"{value} {unit_str}")

    return " ".join(parts)


def format_timestamp(ts: Any, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a timestamp for display.

    Args:
        ts: A datetime object or timestamp string.
        fmt: strftime format string.

    Returns:
        Formatted timestamp string.
    """
    from datetime import datetime

    if ts is None:
        return "-"
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return ts
    if isinstance(ts, datetime):
        return ts.strftime(fmt)
    return str(ts)


def truncate_text(text: str, max_length: int = 50, suffix: str = "...") -> str:
    """Truncate text to a maximum length with a suffix."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def exit_with_error(message: str, code: int = 1) -> None:
    """Print an error message and exit."""
    print_error(message)
    sys.exit(code)


def status_badge(status: str) -> str:
    """Return a colored status badge string."""
    status_colors = {
        # General
        "running": "[green]● running[/]",
        "stopped": "[red]○ stopped[/]",
        "pending": "[yellow]◐ pending[/]",
        "success": "[green]✓ success[/]",
        "failed": "[red]✗ failed[/]",
        "error": "[red]✗ error[/]",
        "enabled": "[green]enabled[/]",
        "disabled": "[dim]disabled[/]",
        "active": "[green]active[/]",
        "inactive": "[dim]inactive[/]",
        "paused": "[yellow]paused[/]",
        # Task / execution states
        "queued": "[yellow]◐ queued[/]",
        "completed": "[green]✓ completed[/]",
        "cancelled": "[dim]○ cancelled[/]",
        "timeout": "[red]⏱ timeout[/]",
        "skipped": "[dim]⊘ skipped[/]",
        "retrying": "[yellow]↻ retrying[/]",
        # Flow / workflow
        "draft": "[dim]draft[/]",
        "published": "[green]published[/]",
        "archived": "[dim]archived[/]",
        # Streaming / message
        "streaming": "[cyan]● streaming[/]",
        # Process
        "healthy": "[green]✓ healthy[/]",
        "degraded": "[yellow]⚠ degraded[/]",
        "unhealthy": "[red]✗ unhealthy[/]",
    }
    return status_colors.get(status.lower(), status)
