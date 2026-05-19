"""CLI commands for workflow templates (file-based service + optional HTTP API)."""

from __future__ import annotations

from typing import Any

import click

from leagent.cli.http import CLIHttpError, get_client
from leagent.cli.utils import (
    console,
    create_table,
    print_dim,
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_text,
    status_badge,
    truncate_text,
)


def _server_available() -> bool:
    try:
        client = get_client()
        return client.health_check()
    except Exception:
        return False


def _get_local_templates() -> list[dict[str, Any]]:
    """Load templates via the local TemplateService."""
    try:
        from leagent.workflow.template_service import TemplateService
        svc = TemplateService()
        return svc.list_templates()
    except Exception:
        return []


def _get_local_categories() -> list[dict[str, Any]]:
    try:
        from leagent.workflow.template_service import TemplateService
        svc = TemplateService()
        return svc.list_categories()
    except Exception:
        return []


def _get_local_template(template_id: str) -> dict[str, Any] | None:
    try:
        from leagent.workflow.template_service import TemplateService
        svc = TemplateService()
        return svc.get_template(template_id)
    except Exception:
        return None


def _get_local_template_info(template_id: str) -> dict[str, Any] | None:
    try:
        from leagent.workflow.template_service import TemplateService
        svc = TemplateService()
        return svc.get_template_info(template_id)
    except Exception:
        return None


@click.group(name="templates")
def templates_group() -> None:
    """Workflow templates: local ``TemplateService`` files and/or ``/api/v1/templates`` when online."""


# ── list ─────────────────────────────────────────────────────────────

@templates_group.command(name="list")
@click.option("--category", "-c", default=None, help="Filter by category.")
@click.option("--search", "-q", default=None, help="Search by name or description.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def list_templates(category: str | None, search: str | None, as_json: bool) -> None:
    """List available workflow templates."""
    if _server_available():
        try:
            client = get_client()
            params: dict[str, Any] = {}
            if category:
                params["category"] = category
            if search:
                params["search"] = search
            result = client.get("/api/v1/templates", params=params)
            templates = result.get("templates", [])
        except CLIHttpError as e:
            print_warning(f"API error: {e}. Loading local templates.")
            templates = _get_local_templates()
    else:
        templates = _get_local_templates()

    if search and not _server_available():
        q = search.lower()
        templates = [
            t for t in templates
            if q in t.get("name", "").lower()
            or q in t.get("description", "").lower()
        ]

    if category and not _server_available():
        templates = [t for t in templates if t.get("category") == category]

    if as_json:
        console.print_json(data=templates)
        return

    if not templates:
        print_info("No templates found.")
        return

    console.print()
    console.rule("[bold cyan]Workflow Templates[/]")
    console.print()

    table = create_table(columns=[
        ("ID", {"style": "cyan"}),
        ("Name", {}),
        ("Category", {}),
        ("Nodes", {"justify": "right"}),
        ("Tags", {}),
        ("Source", {"style": "dim"}),
    ])

    for t in templates:
        tags_str = ", ".join(t.get("tags", [])[:3])
        table.add_row(
            t.get("id", "-"),
            truncate_text(t.get("name", "-"), 35),
            t.get("category", "-"),
            str(t.get("node_count", 0)),
            tags_str or "-",
            t.get("source", "-"),
        )

    console.print(table)
    console.print()
    console.print(f"[dim]{len(templates)} template(s) found[/]")
    console.print()


# ── categories ───────────────────────────────────────────────────────

@templates_group.command(name="categories")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def list_categories(as_json: bool) -> None:
    """List template categories."""
    if _server_available():
        try:
            client = get_client()
            result = client.get("/api/v1/templates/categories")
            categories = result.get("categories", [])
        except CLIHttpError:
            categories = _get_local_categories()
    else:
        categories = _get_local_categories()

    if as_json:
        console.print_json(data=categories)
        return

    if not categories:
        print_info("No categories found.")
        return

    console.print()
    console.rule("[bold cyan]Template Categories[/]")
    console.print()

    for cat in categories:
        icon = cat.get("icon", "📋")
        label = cat.get("label", cat.get("id", "-"))
        count = cat.get("count", 0)
        console.print(f"  {icon} [cyan]{cat.get('id', '-')}[/]  {label}  [dim]({count} templates)[/]")

    console.print()


# ── show ─────────────────────────────────────────────────────────────

@templates_group.command(name="show")
@click.argument("template_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def show_template(template_id: str, as_json: bool) -> None:
    """Show details of a specific template."""
    detail = None

    if _server_available():
        try:
            client = get_client()
            detail = client.get(f"/api/v1/templates/{template_id}")
        except CLIHttpError:
            pass

    if not detail:
        info = _get_local_template_info(template_id)
        definition = _get_local_template(template_id)
        if info:
            detail = {**info, "definition": definition or {}}

    if not detail:
        print_error(f"Template '{template_id}' not found.")
        raise click.Abort()

    if as_json:
        console.print_json(data=detail)
        return

    console.print()
    console.rule(f"[bold cyan]Template: {detail.get('name')}[/]")
    console.print()

    console.print(f"  [bold]ID:[/]          {detail.get('id')}")
    console.print(f"  [bold]Name:[/]        {detail.get('name')}")
    console.print(f"  [bold]Description:[/] {detail.get('description') or '-'}")
    console.print(f"  [bold]Category:[/]    {detail.get('category_label', detail.get('category', '-'))}")
    console.print(f"  [bold]Icon:[/]        {detail.get('icon', '-')}")
    console.print(f"  [bold]Tags:[/]        {', '.join(detail.get('tags', [])) or '-'}")
    console.print(f"  [bold]Nodes:[/]       {detail.get('node_count', 0)}")
    console.print(f"  [bold]Version:[/]     {detail.get('version', '-')}")
    console.print(f"  [bold]Source:[/]      {detail.get('source', '-')}")
    console.print()

    definition = detail.get("definition", {})
    if definition:
        nodes = definition.get("nodes", [])
        if nodes:
            console.print("[bold]Workflow Nodes:[/]")
            for node in nodes[:10]:
                ntype = node.get("type", node.get("node_type", "-"))
                nname = node.get("name", node.get("label", node.get("id", "-")))
                console.print(f"  [dim]•[/] {ntype}: [cyan]{nname}[/]")
            if len(nodes) > 10:
                console.print(f"  [dim]  ... and {len(nodes) - 10} more[/]")
            console.print()


# ── apply ────────────────────────────────────────────────────────────

@templates_group.command(name="apply")
@click.argument("template_id")
@click.option("--name", "-n", default=None, help="Name for the created flow.")
@click.option("--description", "-d", default=None, help="Description for the created flow.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def apply_template(template_id: str, name: str | None, description: str | None, as_json: bool) -> None:
    """Create a new flow from a template (requires server)."""
    if not _server_available():
        print_error("Server not running. Template apply requires the API.")
        print_info("Start the server with: leagent app start")
        raise click.Abort()

    if not name:
        info = None
        try:
            client = get_client()
            info = client.get(f"/api/v1/templates/{template_id}")
        except CLIHttpError:
            info = _get_local_template_info(template_id)

        default_name = info.get("name", template_id) if info else template_id
        name = prompt_text("Flow name", default=f"{default_name} (from template)")

    body: dict[str, Any] = {}
    if name:
        body["name"] = name
    if description:
        body["description"] = description

    try:
        client = get_client()
        result = client.post(f"/api/v1/templates/{template_id}/apply", json=body)
    except CLIHttpError as e:
        print_error(f"Apply failed: {e}")
        raise click.Abort()

    if as_json:
        console.print_json(data=result)
        return

    flow_id = result.get("flow_id", "unknown")
    flow_name = result.get("name", name)
    print_success(f"Flow '{flow_name}' created from template.")
    console.print(f"  [dim]Flow ID:[/] {flow_id}")
    console.print(f"  [dim]Message:[/] {result.get('message', '-')}")
    console.print()
    print_dim(f"Edit in UI or run with: leagent workflows run {flow_id}")
