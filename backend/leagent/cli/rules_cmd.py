"""CLI commands for the declarative rule engine (YAML packs on disk)."""

from __future__ import annotations

import asyncio
import json
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
)
from leagent.config.constants import RULES_DIR


def _cli_rules_dir() -> Path:
    from leagent.config.settings import get_settings

    raw = (get_settings().rules_directory or "").strip()
    return Path(raw).expanduser().resolve() if raw else RULES_DIR


@click.group(name="rules")
def rules_group() -> None:
    """Declarative YAML rule packs (``RuleEngine``) loaded from ``RULES_DIR`` / settings."""


@rules_group.command(name="list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def list_rules(as_json: bool) -> None:
    """List rule sets from the local rules directory."""
    from leagent.rules.loader import RuleLoader

    rules_dir = _cli_rules_dir()
    if not rules_dir.exists():
        print_info(f"Rules directory does not exist: {rules_dir}")
        print_dim("Run 'leagent init' to create it.")
        return

    loader = RuleLoader()
    try:
        rule_sets = loader.load_directory(rules_dir)
    except Exception as exc:
        print_error(f"Failed to load rules: {exc}")
        raise click.Abort()

    if not rule_sets:
        print_info("No rule sets found.")
        print_dim(f"Add YAML rule files to: {rules_dir}")
        return

    if as_json:
        data = [
            {"id": rs.id, "name": rs.name, "enabled": rs.enabled, "rules": len(rs.rules), "tags": rs.tags}
            for rs in rule_sets.values()
        ]
        console.print_json(data=data)
        return

    console.print()
    console.rule("[bold cyan]Rule Sets[/]")
    console.print()

    table = create_table(columns=[
        ("ID", {"style": "cyan"}),
        ("Name", {}),
        ("Rules", {}),
        ("Enabled", {}),
        ("Tags", {}),
    ])

    for rs in sorted(rule_sets.values(), key=lambda r: r.id):
        enabled = "[green]yes[/]" if rs.enabled else "[dim]no[/]"
        table.add_row(rs.id, rs.name, str(len(rs.rules)), enabled, ", ".join(rs.tags) or "-")

    console.print(table)
    console.print()
    print_dim(f"Rules directory: {rules_dir}")
    console.print()


@rules_group.command(name="show")
@click.argument("rule_set_id")
def show_rule_set(rule_set_id: str) -> None:
    """Show detailed information about a rule set."""
    from leagent.rules.loader import RuleLoader

    rules_dir = _cli_rules_dir()
    if not rules_dir.exists():
        print_error(f"Rules directory does not exist: {rules_dir}")
        raise click.Abort()

    loader = RuleLoader()
    try:
        rule_sets = loader.load_directory(rules_dir)
    except Exception as exc:
        print_error(f"Failed to load rules: {exc}")
        raise click.Abort()

    rs = rule_sets.get(rule_set_id)
    if not rs:
        print_error(f"Rule set '{rule_set_id}' not found.")
        print_dim(f"Available: {', '.join(rule_sets.keys()) or 'none'}")
        raise click.Abort()

    console.print()
    console.rule(f"[bold cyan]Rule Set: {rs.name}[/]")
    console.print()
    console.print(f"  [bold]ID:[/]          {rs.id}")
    console.print(f"  [bold]Version:[/]     {rs.version}")
    console.print(f"  [bold]Enabled:[/]     {rs.enabled}")
    console.print(f"  [bold]Description:[/] {rs.description or '-'}")
    console.print(f"  [bold]Tags:[/]        {', '.join(rs.tags) or '-'}")
    console.print()

    if rs.rules:
        table = create_table(columns=[
            ("ID", {"style": "cyan"}),
            ("Name", {}),
            ("Type", {}),
            ("Severity", {}),
            ("Enabled", {}),
        ])
        for rule in rs.rules:
            sev_style = {"error": "red", "warning": "yellow", "info": "blue"}.get(rule.severity.value, "")
            sev = f"[{sev_style}]{rule.severity.value}[/{sev_style}]" if sev_style else rule.severity.value
            enabled = "[green]yes[/]" if rule.enabled else "[dim]no[/]"
            table.add_row(rule.id, rule.name, rule.condition.type.value, sev, enabled)
        console.print(table)
    else:
        print_dim("  No rules defined.")
    console.print()


@rules_group.command(name="validate")
@click.argument("path", type=click.Path(exists=True))
def validate_rules(path: str) -> None:
    """Validate a YAML rule file without loading into the engine."""
    from leagent.rules.loader import RuleLoader, RuleValidator

    file_path = Path(path)
    loader = RuleLoader()
    validator = RuleValidator()

    try:
        rule_set = loader.load_file(file_path)
    except Exception as exc:
        print_error(f"Load failed: {exc}")
        raise click.Abort()

    errors = validator.validate_rule_set(rule_set)
    if errors:
        print_warning(f"Validation found {len(errors)} issue(s):")
        for err in errors:
            console.print(f"  [yellow]•[/] {err}")
    else:
        print_success(f"Rule set '{rule_set.id}' is valid ({len(rule_set.rules)} rules).")


@rules_group.command(name="evaluate")
@click.argument("rule_set_id")
@click.option("--data", "-d", "data_json", required=True, help="JSON data to evaluate against.")
@click.option("--tags", "-t", default=None, help="Comma-separated tag filter.")
def evaluate_rule_set(rule_set_id: str, data_json: str, tags: str | None) -> None:
    """Evaluate a rule set against provided JSON data (locally)."""
    from leagent.rules.loader import RuleLoader
    from leagent.rules.engine import RuleEngine

    try:
        data = json.loads(data_json)
    except json.JSONDecodeError as exc:
        print_error(f"Invalid JSON: {exc}")
        raise click.Abort()

    rules_dir = _cli_rules_dir()
    if not rules_dir.exists():
        print_error(f"Rules directory does not exist: {rules_dir}")
        raise click.Abort()

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    async def _eval() -> None:
        engine = RuleEngine()
        await engine.safe_load_directory(rules_dir)

        if rule_set_id not in engine.list_rule_sets():
            print_error(f"Rule set '{rule_set_id}' not found.")
            raise click.Abort()

        result = await engine.evaluate(rule_set_id, data, tags=tag_list)

        console.print()
        status_text = "[green]PASSED[/]" if result.passed else "[red]FAILED[/]"
        console.print(f"  Result: {status_text}")
        console.print(f"  Rules evaluated: {result.total_rules}")
        console.print(f"  Errors: {result.error_count} | Warnings: {result.warning_count} | Info: {result.info_count}")
        console.print(f"  Time: {result.execution_time_ms:.1f}ms")

        if result.results:
            console.print()
            for r in result.results:
                icon = "[green]✓[/]" if r.passed else "[red]✗[/]"
                console.print(f"  {icon} {r.rule_name}: {r.message or 'ok'}")
        console.print()

    asyncio.run(_eval())


@rules_group.command(name="create")
@click.argument("name", default="new-rules")
@click.option("--output", "-o", default=None, help="Output directory (default: RULES_DIR).")
def create_rule_set(name: str, output: str | None) -> None:
    """Scaffold a new rule set YAML file."""
    target_dir = Path(output) if output else _cli_rules_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{name}.yaml"
    target = target_dir / filename

    if target.exists():
        print_warning(f"File already exists: {target}")
        raise click.Abort()

    template = f"""\
id: {name}
name: "{name.replace('-', ' ').title()}"
description: "TODO: Describe this rule set"
version: "1.0.0"
enabled: true
tags: []
rules:
  - id: example-rule
    name: "Example Rule"
    condition:
      type: threshold
      params:
        value: "{{{{amount}}}}"
        max: 10000
    severity: warning
    message: "Value {{{{amount}}}} exceeds threshold"
    enabled: true
    tags: []
"""
    target.write_text(template, encoding="utf-8")
    print_success(f"Created rule set scaffold: {target}")
    print_dim("Edit the file to define your rules, then run 'leagent rules validate' to check.")


@rules_group.command(name="reload")
def reload_rules() -> None:
    """Reload rules via the server API (requires running server)."""
    from leagent.cli.http import CLIHttpError, get_client

    try:
        client = get_client()
        result = client.post("/api/v1/rules/reload")
        print_success(f"Rules reloaded: {result.get('rule_sets', 0)} rule set(s)")
    except CLIHttpError as exc:
        print_error(f"Reload failed: {exc}")
        raise click.Abort()
