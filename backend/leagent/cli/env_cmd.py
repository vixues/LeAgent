"""CLI helpers for LeAgent dotenv files (mirrors what ``leagent.config`` loads at startup)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import click

from leagent.cli.utils import (
    console,
    create_table,
    print_dim,
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
    prompt_text,
)
from leagent.config.constants import LEAGENT_HOME


def _get_env_file() -> Path:
    """Get the path to the .env file."""
    local_env = Path.cwd() / ".env"
    if local_env.exists():
        return local_env

    home_env = LEAGENT_HOME / ".env"
    return home_env


def _load_env_file(env_path: Path) -> dict[str, str]:
    """Load environment variables from a .env file."""
    env_vars: dict[str, str] = {}

    if not env_path.exists():
        return env_vars

    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()

                if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]

                env_vars[key] = value

    return env_vars


def _save_env_file(env_path: Path, env_vars: dict[str, str], comments: list[str] | None = None) -> None:
    """Save environment variables to a .env file."""
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []

    if comments:
        for comment in comments:
            if not comment.startswith("#"):
                comment = f"# {comment}"
            lines.append(comment)
        lines.append("")

    for key, value in sorted(env_vars.items()):
        if " " in value or '"' in value or "'" in value:
            value = f'"{value}"'
        lines.append(f"{key}={value}")

    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


SENSITIVE_PATTERNS = [
    r".*_KEY$",
    r".*_SECRET$",
    r".*_TOKEN$",
    r".*_PASSWORD$",
    r".*_CREDENTIALS$",
    r"^API_KEY$",
    r"^SECRET$",
    r"^PASSWORD$",
]


def _is_sensitive(key: str) -> bool:
    """Check if a key is likely to contain sensitive data."""
    for pattern in SENSITIVE_PATTERNS:
        if re.match(pattern, key, re.IGNORECASE):
            return True
    return False


def _mask_value(value: str) -> str:
    """Mask a sensitive value for display."""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


@click.group(name="env")
def env_group() -> None:
    """Inspect or edit ``.env`` (cwd wins, else ``LEAGENT_HOME/.env``) for ``pydantic-settings`` / process env."""


@env_group.command(name="list")
@click.option("--all", "-a", "show_all", is_flag=True, help="Show all environment variables including system.")
@click.option("--reveal", "-r", is_flag=True, help="Reveal sensitive values (use with caution).")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def list_env(show_all: bool, reveal: bool, as_json: bool) -> None:
    """List environment variables."""
    env_path = _get_env_file()
    file_vars = _load_env_file(env_path)

    if show_all:
        all_vars = dict(os.environ)
        all_vars.update(file_vars)
        display_vars = all_vars
        source = "environment + .env"
    else:
        display_vars = {k: v for k, v in file_vars.items()}
        leagent_vars = {k: v for k, v in os.environ.items() if k.startswith("LEAGENT_")}
        display_vars.update(leagent_vars)
        source = str(env_path) if env_path.exists() else "not found"

    if as_json:
        if not reveal:
            display_vars = {k: (_mask_value(v) if _is_sensitive(k) else v) for k, v in display_vars.items()}
        console.print_json(data=display_vars)
        return

    console.print()
    console.rule("[bold cyan]Environment Variables[/]")
    console.print()
    console.print(f"  [dim]Source:[/] {source}")
    console.print()

    if not display_vars:
        print_info("No environment variables found.")
        print_dim(f"Create a .env file at {env_path}")
        return

    table = create_table(
        columns=[
            ("Variable", {"style": "cyan"}),
            ("Value", {}),
            ("Source", {"style": "dim"}),
        ],
    )

    for key in sorted(display_vars.keys()):
        value = display_vars[key]
        is_from_file = key in file_vars
        src = "file" if is_from_file else "env"

        if _is_sensitive(key) and not reveal:
            display_value = _mask_value(value)
        else:
            display_value = value[:60] + "..." if len(value) > 60 else value

        table.add_row(key, display_value, src)

    console.print(table)
    console.print()

    if not reveal:
        print_dim("Sensitive values are masked. Use --reveal to show them.")
    console.print()


@env_group.command(name="set")
@click.argument("name")
@click.argument("value", required=False)
@click.option("--secret", "-s", is_flag=True, help="Prompt for value securely (hidden input).")
def set_env(name: str, value: str | None, secret: bool) -> None:
    """Set an environment variable in the .env file."""
    env_path = _get_env_file()
    env_vars = _load_env_file(env_path)

    if value is None:
        if secret:
            value = prompt_text(f"Enter value for {name}", password=True)
        else:
            value = prompt_text(f"Enter value for {name}")

    if not value:
        print_error("Value cannot be empty.")
        raise click.Abort()

    name = name.upper()
    was_existing = name in env_vars
    env_vars[name] = value

    try:
        _save_env_file(env_path, env_vars)

        if was_existing:
            print_success(f"Updated {name} in {env_path}")
        else:
            print_success(f"Added {name} to {env_path}")

        if _is_sensitive(name):
            print_dim("Value contains sensitive data and will be masked in listings.")

    except Exception as e:
        print_error(f"Failed to save environment variable: {e}")
        raise click.Abort()


@env_group.command(name="unset")
@click.argument("names", nargs=-1, required=True)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def unset_env(names: tuple[str, ...], yes: bool) -> None:
    """Remove environment variables from the .env file."""
    env_path = _get_env_file()
    env_vars = _load_env_file(env_path)

    names_upper = [n.upper() for n in names]
    to_remove = [n for n in names_upper if n in env_vars]

    if not to_remove:
        print_warning("None of the specified variables exist in .env file.")
        return

    if not yes and not prompt_confirm(f"Remove {len(to_remove)} variable(s)?"):
        print_info("Cancelled.")
        return

    for name in to_remove:
        del env_vars[name]

    try:
        _save_env_file(env_path, env_vars)
        print_success(f"Removed: {', '.join(to_remove)}")
    except Exception as e:
        print_error(f"Failed to update environment file: {e}")
        raise click.Abort()


@env_group.command(name="get")
@click.argument("name")
@click.option("--reveal", "-r", is_flag=True, help="Reveal sensitive value.")
def get_env(name: str, reveal: bool) -> None:
    """Get the value of a specific environment variable."""
    name = name.upper()

    env_path = _get_env_file()
    file_vars = _load_env_file(env_path)

    value = file_vars.get(name) or os.environ.get(name)

    if value is None:
        print_error(f"Variable '{name}' not found.")
        raise click.Abort()

    source = "file" if name in file_vars else "environment"

    if _is_sensitive(name) and not reveal:
        display_value = _mask_value(value)
        print_warning("Value is masked. Use --reveal to show the full value.")
    else:
        display_value = value

    console.print(f"[cyan]{name}[/]={display_value}")
    print_dim(f"Source: {source}")


@env_group.command(name="export")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path.")
@click.option("--format", "-f", "output_format", type=click.Choice(["env", "json", "shell"]), default="env", help="Export format.")
@click.option("--filter", "prefix_filter", default=None, help="Only export variables matching prefix.")
def export_env(output: str | None, output_format: str, prefix_filter: str | None) -> None:
    """Export environment variables to a file."""
    env_path = _get_env_file()
    env_vars = _load_env_file(env_path)

    if prefix_filter:
        prefix_upper = prefix_filter.upper()
        env_vars = {k: v for k, v in env_vars.items() if k.startswith(prefix_upper)}

    if not env_vars:
        print_warning("No environment variables to export.")
        return

    if output:
        output_path = Path(output)
    else:
        output_path = Path.cwd() / f"env_export.{output_format}"

    try:
        if output_format == "json":
            import json

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(env_vars, f, indent=2)

        elif output_format == "shell":
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("#!/bin/bash\n\n")
                for key, value in sorted(env_vars.items()):
                    escaped_value = value.replace("'", "'\\''")
                    f.write(f"export {key}='{escaped_value}'\n")

        else:
            _save_env_file(output_path, env_vars, comments=[
                "LeAgent Environment Export",
                f"Exported from {env_path}",
            ])

        print_success(f"Exported {len(env_vars)} variable(s) to {output_path}")

    except Exception as e:
        print_error(f"Failed to export environment variables: {e}")
        raise click.Abort()


@env_group.command(name="edit")
def edit_env() -> None:
    """Open the .env file in your default editor."""
    env_path = _get_env_file()

    if not env_path.exists():
        if prompt_confirm(f"Create new .env file at {env_path}?"):
            env_path.parent.mkdir(parents=True, exist_ok=True)
            env_path.touch()
        else:
            print_info("Cancelled.")
            return

    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "nano"))

    try:
        import subprocess

        subprocess.run([editor, str(env_path)])
        print_success(f"Edited {env_path}")
    except Exception as e:
        print_error(f"Failed to open editor: {e}")
        print_info(f"Manually edit: {env_path}")


@env_group.command(name="validate")
def validate_env() -> None:
    """Validate environment configuration for LeAgent."""
    env_path = _get_env_file()
    env_vars = _load_env_file(env_path)

    all_vars = dict(os.environ)
    all_vars.update(env_vars)

    required_vars: list[tuple[str, str]] = []

    optional_vars = [
        ("DB_DRIVER", "SQLAlchemy async driver (default sqlite+aiosqlite)"),
        ("DB_SQLITE_PATH", "SQLite database file path (optional)"),
        ("REDIS_URL", "Redis connection string"),
        ("LEAGENT_SECRET_KEY", "Application secret key"),
        ("OPENAI_API_KEY", "OpenAI API key"),
        ("DASHSCOPE_API_KEY", "DashScope API key"),
    ]

    console.print()
    console.rule("[bold cyan]Environment Validation[/]")
    console.print()

    all_valid = True

    console.print("[bold]Required Variables:[/]")
    for var_name, description in required_vars:
        value = all_vars.get(var_name)
        if value:
            console.print(f"  [green]✓[/] {var_name}: [dim]{description}[/]")
        else:
            console.print(f"  [red]✗[/] {var_name}: [dim]{description}[/] [red](missing)[/]")
            all_valid = False

    console.print()
    console.print("[bold]Optional Variables:[/]")
    for var_name, description in optional_vars:
        value = all_vars.get(var_name)
        if value:
            console.print(f"  [green]✓[/] {var_name}: [dim]{description}[/]")
        else:
            console.print(f"  [yellow]○[/] {var_name}: [dim]{description}[/] [dim](not set)[/]")

    console.print()

    if all_valid:
        print_success("All required environment variables are configured.")
    else:
        print_error("Some required environment variables are missing.")
        print_info("Set missing variables with: leagent env set <NAME> <VALUE>")
