"""CLI commands to reclaim disk under ``LEAGENT_HOME`` working dirs (uploads, cache, logs, …)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import click

from leagent.cli.utils import (
    console,
    create_table,
    format_bytes,
    print_dim,
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
)
from leagent.config.constants import (
    CACHE_DIR,
    LOG_DIR,
    OUTPUT_DIR,
    TEMP_DIR,
    UPLOAD_DIR,
    LEAGENT_HOME,
)


def _get_dir_size(path: Path) -> int:
    """Calculate total size of a directory."""
    if not path.exists():
        return 0

    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass

    return total


def _count_files(path: Path) -> int:
    """Count files in a directory."""
    if not path.exists():
        return 0

    try:
        return sum(1 for _ in path.rglob("*") if _.is_file())
    except (OSError, PermissionError):
        return 0


def _clean_directory(path: Path, pattern: str = "*", dry_run: bool = False) -> tuple[int, int]:
    """Clean files from a directory matching pattern.

    Returns:
        Tuple of (files_removed, bytes_freed)
    """
    if not path.exists():
        return 0, 0

    files_removed = 0
    bytes_freed = 0

    try:
        for entry in path.glob(pattern):
            if entry.is_file():
                size = entry.stat().st_size
                if not dry_run:
                    entry.unlink()
                files_removed += 1
                bytes_freed += size
            elif entry.is_dir() and pattern == "*":
                size = _get_dir_size(entry)
                if not dry_run:
                    shutil.rmtree(entry)
                files_removed += _count_files(entry)
                bytes_freed += size
    except (OSError, PermissionError) as e:
        print_warning(f"Could not clean some files: {e}")

    return files_removed, bytes_freed


@click.command(name="clean")
@click.option("--temp", "-t", is_flag=True, help="Clean temporary files.")
@click.option("--cache", "-c", is_flag=True, help="Clean cache files.")
@click.option("--logs", "-l", is_flag=True, help="Clean log files.")
@click.option("--uploads", "-u", is_flag=True, help="Clean uploaded files.")
@click.option("--outputs", "-o", is_flag=True, help="Clean output files.")
@click.option("--all", "-a", "clean_all", is_flag=True, help="Clean everything.")
@click.option("--dry-run", "-n", is_flag=True, help="Show what would be cleaned without deleting.")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.option("--older-than", default=None, type=int, help="Only clean files older than N days.")
def clean_cmd(
    temp: bool,
    cache: bool,
    logs: bool,
    uploads: bool,
    outputs: bool,
    clean_all: bool,
    dry_run: bool,
    yes: bool,
    older_than: int | None,
) -> None:
    """Remove temp/cache/log/upload/output trees (scoped flags or ``--all``).

    With no category flags, prints a usage hint and disk snapshot instead of deleting.
    """
    if not any([temp, cache, logs, uploads, outputs, clean_all]):
        _show_cleanup_status()
        return

    targets: list[tuple[str, Path]] = []

    if clean_all or temp:
        targets.append(("Temporary files", TEMP_DIR))

    if clean_all or cache:
        targets.append(("Cache", CACHE_DIR))

    if clean_all or logs:
        targets.append(("Logs", LOG_DIR))

    if clean_all or uploads:
        targets.append(("Uploads", UPLOAD_DIR))

    if clean_all or outputs:
        targets.append(("Outputs", OUTPUT_DIR))

    console.print()
    console.rule("[bold cyan]Cleanup Preview[/]")
    console.print()

    table = create_table(
        columns=[
            ("Category", {"style": "cyan"}),
            ("Path", {"style": "dim"}),
            ("Files", {"justify": "right"}),
            ("Size", {"justify": "right"}),
        ],
    )

    total_files = 0
    total_size = 0

    for name, path in targets:
        if older_than:
            files, size = _get_old_files_stats(path, older_than)
        else:
            files = _count_files(path)
            size = _get_dir_size(path)

        total_files += files
        total_size += size
        table.add_row(name, str(path), str(files), format_bytes(size))

    console.print(table)
    console.print()
    console.print(f"[bold]Total:[/] {total_files} files, {format_bytes(total_size)}")
    console.print()

    if dry_run:
        print_info("Dry run mode. No files will be deleted.")
        return

    if total_files == 0:
        print_info("Nothing to clean.")
        return

    if not yes and not prompt_confirm(f"Delete {total_files} files ({format_bytes(total_size)})?"):
        print_info("Cancelled.")
        return

    console.print()
    console.print("[bold]Cleaning...[/]")

    cleaned_files = 0
    cleaned_size = 0

    for name, path in targets:
        if older_than:
            files, size = _clean_old_files(path, older_than)
        else:
            files, size = _clean_directory(path)

        if files > 0:
            console.print(f"  [green]✓[/] {name}: {files} files, {format_bytes(size)}")
            cleaned_files += files
            cleaned_size += size
        else:
            console.print(f"  [dim]○[/] {name}: nothing to clean")

    console.print()
    print_success(f"Cleaned {cleaned_files} files, freed {format_bytes(cleaned_size)}")


def _show_cleanup_status() -> None:
    """Show current disk usage status."""
    console.print()
    console.rule("[bold cyan]Disk Usage[/]")
    console.print()

    categories = [
        ("Temporary files", TEMP_DIR, "--temp"),
        ("Cache", CACHE_DIR, "--cache"),
        ("Logs", LOG_DIR, "--logs"),
        ("Uploads", UPLOAD_DIR, "--uploads"),
        ("Outputs", OUTPUT_DIR, "--outputs"),
    ]

    table = create_table(
        columns=[
            ("Category", {"style": "cyan"}),
            ("Files", {"justify": "right"}),
            ("Size", {"justify": "right"}),
            ("Clean flag", {"style": "dim"}),
        ],
    )

    total_files = 0
    total_size = 0

    for name, path, flag in categories:
        files = _count_files(path)
        size = _get_dir_size(path)
        total_files += files
        total_size += size
        table.add_row(name, str(files), format_bytes(size), flag)

    console.print(table)
    console.print()
    console.print(f"[bold]Total:[/] {total_files} files, {format_bytes(total_size)}")
    console.print()

    console.print("[bold]Usage:[/]")
    console.print("  leagent clean --temp       # Clean temp files")
    console.print("  leagent clean --cache      # Clean cache")
    console.print("  leagent clean --logs       # Clean logs")
    console.print("  leagent clean --all        # Clean everything")
    console.print("  leagent clean --all --dry-run  # Preview without deleting")
    console.print()


def _get_old_files_stats(path: Path, days: int) -> tuple[int, int]:
    """Get stats for files older than N days."""
    import time

    if not path.exists():
        return 0, 0

    cutoff = time.time() - (days * 86400)
    files = 0
    size = 0

    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                try:
                    stat = entry.stat()
                    if stat.st_mtime < cutoff:
                        files += 1
                        size += stat.st_size
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass

    return files, size


def _clean_old_files(path: Path, days: int) -> tuple[int, int]:
    """Clean files older than N days."""
    import time

    if not path.exists():
        return 0, 0

    cutoff = time.time() - (days * 86400)
    files_removed = 0
    bytes_freed = 0

    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                try:
                    stat = entry.stat()
                    if stat.st_mtime < cutoff:
                        size = stat.st_size
                        entry.unlink()
                        files_removed += 1
                        bytes_freed += size
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass

    return files_removed, bytes_freed


@click.command(name="prune")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def prune_cmd(yes: bool) -> None:
    """Remove unused data and optimize storage.

    This command removes:
    - Orphaned temporary files
    - Expired cache entries
    - Old log files (> 30 days)
    - Unused uploads without references
    """
    console.print()
    console.rule("[bold cyan]Pruning LeAgent Data[/]")
    console.print()

    tasks = [
        ("Orphaned temp files", _prune_temp),
        ("Expired cache entries", _prune_cache),
        ("Old log files (>30 days)", _prune_logs),
    ]

    if not yes:
        console.print("This will remove:")
        for name, _ in tasks:
            console.print(f"  • {name}")
        console.print()

        if not prompt_confirm("Continue?"):
            print_info("Cancelled.")
            return

    console.print()
    total_freed = 0

    for name, prune_func in tasks:
        try:
            freed = prune_func()
            if freed > 0:
                console.print(f"  [green]✓[/] {name}: freed {format_bytes(freed)}")
                total_freed += freed
            else:
                console.print(f"  [dim]○[/] {name}: nothing to prune")
        except Exception as e:
            console.print(f"  [red]✗[/] {name}: {e}")

    console.print()
    print_success(f"Pruning complete. Total freed: {format_bytes(total_freed)}")


def _prune_temp() -> int:
    """Prune orphaned temporary files."""
    import time

    if not TEMP_DIR.exists():
        return 0

    cutoff = time.time() - 86400
    freed = 0

    for entry in TEMP_DIR.iterdir():
        try:
            if entry.stat().st_mtime < cutoff:
                if entry.is_file():
                    freed += entry.stat().st_size
                    entry.unlink()
                elif entry.is_dir():
                    freed += _get_dir_size(entry)
                    shutil.rmtree(entry)
        except (OSError, PermissionError):
            pass

    return freed


def _prune_cache() -> int:
    """Prune expired cache entries."""
    import time

    if not CACHE_DIR.exists():
        return 0

    cutoff = time.time() - (7 * 86400)
    freed = 0

    for entry in CACHE_DIR.rglob("*"):
        if entry.is_file():
            try:
                if entry.stat().st_mtime < cutoff:
                    freed += entry.stat().st_size
                    entry.unlink()
            except (OSError, PermissionError):
                pass

    return freed


def _prune_logs() -> int:
    """Prune old log files."""
    import time

    if not LOG_DIR.exists():
        return 0

    cutoff = time.time() - (30 * 86400)
    freed = 0

    for entry in LOG_DIR.rglob("*.log*"):
        if entry.is_file():
            try:
                if entry.stat().st_mtime < cutoff:
                    freed += entry.stat().st_size
                    entry.unlink()
            except (OSError, PermissionError):
                pass

    return freed
