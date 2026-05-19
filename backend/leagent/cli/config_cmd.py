"""CLI commands for project-level .leagent/ configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import yaml

from leagent.cli.utils import (
    console,
    print_dim,
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
)

PROJECT_DIR_NAME = ".leagent"


def get_project_dir(cwd: Path | None = None) -> Path:
    """Return the .leagent/ directory for the current project."""
    return (cwd or Path.cwd()) / PROJECT_DIR_NAME


def find_project_dir(start: Path | None = None) -> Path | None:
    """Walk up from *start* looking for an existing .leagent/ directory."""
    current = start or Path.cwd()
    home = Path.home()
    while current != current.parent:
        candidate = current / PROJECT_DIR_NAME
        if candidate.is_dir():
            return candidate
        if current == home:
            break
        current = current.parent
    return None


def load_project_config(project_dir: Path | None = None) -> dict[str, Any]:
    """Load and return the project config, or an empty dict."""
    pdir = project_dir or find_project_dir()
    if not pdir:
        return {}
    config_path = pdir / "config.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_project_config(data: dict[str, Any], project_dir: Path) -> None:
    """Write the project config back to disk."""
    config_path = project_dir / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


_DEFAULT_PROJECT_CONFIG = {
    "version": "1",
    "agent": {
        "mode": "hybrid",
        "model_tier": "tier1",
        "verbose": False,
    },
    "rules": {
        "auto_load": True,
    },
    "skills": {
        "auto_load": True,
    },
}


@click.group(name="config")
def config_group() -> None:
    """Per-repository ``.leagent/`` (project memory, skills, rules) merged into prompt context."""


@config_group.command(name="init")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing config.")
def config_init(force: bool) -> None:
    """Initialize a .leagent/ directory in the current project."""
    project_dir = get_project_dir()

    if project_dir.exists() and not force:
        print_warning(f"Project directory already exists: {project_dir}")
        if not prompt_confirm("Reinitialize?"):
            return

    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "rules").mkdir(exist_ok=True)
    (project_dir / "skills").mkdir(exist_ok=True)

    save_project_config(_DEFAULT_PROJECT_CONFIG, project_dir)

    # Create a placeholder rule set
    sample_rule = project_dir / "rules" / "sample_rules.yaml"
    if not sample_rule.exists():
        sample_rule.write_text(
            "id: sample-rules\n"
            "name: Sample Rules\n"
            "description: Example rule set — customize or replace\n"
            "enabled: true\n"
            "rules:\n"
            "  - id: example-threshold\n"
            '    name: "Amount limit"\n'
            "    condition:\n"
            "      type: threshold\n"
            "      params:\n"
            "        value: \"{{amount}}\"\n"
            "        max: 10000\n"
            "    severity: warning\n"
            '    message: "Amount {{amount}} exceeds threshold"\n',
            encoding="utf-8",
        )

    # Create a placeholder SKILL.md
    sample_skill_dir = project_dir / "skills" / "project-helper"
    sample_skill_dir.mkdir(parents=True, exist_ok=True)
    sample_skill = sample_skill_dir / "SKILL.md"
    if not sample_skill.exists():
        sample_skill.write_text(
            "---\n"
            "description: Project-specific helper skill\n"
            "when_to_use: When working with this project\n"
            "tags: [project]\n"
            "---\n\n"
            "# Project Helper\n\n"
            "Add project-specific instructions here.\n"
            "The agent will load this skill when relevant.\n",
            encoding="utf-8",
        )

    print_success(f"Project initialized at {project_dir}")
    print_dim("  config.yaml  — project configuration")
    print_dim("  rules/       — project-local rule sets")
    print_dim("  skills/      — project-local skills (SKILL.md)")


@config_group.command(name="show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def config_show(as_json: bool) -> None:
    """Show the merged configuration (global + project)."""
    from leagent.config.constants import LEAGENT_HOME

    project_dir = find_project_dir()
    project_config = load_project_config(project_dir)

    if as_json:
        import json
        console.print_json(data={
            "leagent_home": str(LEAGENT_HOME),
            "project_dir": str(project_dir) if project_dir else None,
            "project_config": project_config,
        })
        return

    console.print()
    console.rule("[bold cyan]LeAgent Configuration[/]")
    console.print()
    console.print(f"  [bold]Global home:[/]   {LEAGENT_HOME}")
    console.print(f"  [bold]Project dir:[/]   {project_dir or '[dim]none (run leagent config init)[/]'}")
    console.print()

    if project_config:
        console.print("[bold]Project config:[/]")
        for key, value in project_config.items():
            if isinstance(value, dict):
                console.print(f"  [cyan]{key}:[/]")
                for k, v in value.items():
                    console.print(f"    {k}: {v}")
            else:
                console.print(f"  [cyan]{key}:[/] {value}")
    else:
        print_dim("  No project configuration found.")
    console.print()


@config_group.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a project config value (dot-notation: agent.mode=react)."""
    project_dir = find_project_dir()
    if not project_dir:
        print_error("No .leagent/ directory found. Run: leagent config init")
        raise click.Abort()

    config = load_project_config(project_dir)

    # Support dot-notation
    keys = key.split(".")
    target = config
    for k in keys[:-1]:
        if k not in target or not isinstance(target[k], dict):
            target[k] = {}
        target = target[k]

    # Type coercion
    if value.lower() in ("true", "false"):
        target[keys[-1]] = value.lower() == "true"
    elif value.isdigit():
        target[keys[-1]] = int(value)
    else:
        try:
            target[keys[-1]] = float(value)
        except ValueError:
            target[keys[-1]] = value

    save_project_config(config, project_dir)
    print_success(f"Set {key} = {target[keys[-1]]}")
