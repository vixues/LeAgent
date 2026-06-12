"""Checklist Generator Tool - Generate checklists from rules and workflows.

Creates structured checklists with status tracking and multiple export formats.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class ChecklistGeneratorTool(SyncTool):
    """Generate checklists from workflow definitions, rules, or manual input.

    Features:
    - Create checklists from workflow YAML/JSON files
    - Manual checklist definition with items and groups
    - Status tracking (pending, in_progress, completed, blocked)
    - Priority levels and due dates
    - Export to Markdown, JSON, HTML, or PDF
    - Nested/hierarchical checklists
    - Progress calculation
    """

    name = "checklist_generator"
    description = (
        "Generate checklists from workflows, rules, or manual definitions. "
        "Supports status tracking, priorities, and export to Markdown, JSON, HTML, or PDF."
    )
    category = ToolCategory.GEN
    version = "1.0.0"
    timeout_sec = 60
    aliases = ["checklist", "checklist_demo", "todo_gen"]
    search_hint = "checklist generate workflow status priority export markdown JSON HTML PDF"
    is_concurrency_safe = True
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000
    path_params = ("source_path",)
    output_path_params = ("output_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "output_path": {
                    "type": "string",
                    "description": (
                        "Optional path to save the checklist. Omit for inline chat display "
                        "(returns content in the tool result). When saving, use a session-relative "
                        "path or filename under the upload workspace, not system paths like /dev/null."
                    ),
                },
                "output_format": {
                    "type": "string",
                    "enum": ["markdown", "json", "html", "pdf"],
                    "description": "Output format. Defaults to markdown.",
                },
                "source_type": {
                    "type": "string",
                    "enum": ["workflow", "rules", "manual"],
                    "description": "Source type for checklist generation.",
                },
                "source_path": {
                    "type": "string",
                    "description": "Path to workflow/rules file (for workflow/rules source types).",
                },
                "title": {
                    "type": "string",
                    "description": "Checklist title.",
                },
                "description": {
                    "type": "string",
                    "description": "Checklist description.",
                },
                "metadata": {
                    "type": "object",
                    "description": "Additional metadata.",
                    "properties": {
                        "created_by": {"type": "string"},
                        "created_at": {"type": "string"},
                        "version": {"type": "string"},
                        "category": {"type": "string"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
                "groups": {
                    "type": "array",
                    "description": "Checklist groups (for manual source type).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "text": {"type": "string"},
                                        "status": {
                                            "type": "string",
                                            "enum": ["pending", "in_progress", "completed", "blocked", "skipped"],
                                        },
                                        "priority": {
                                            "type": "string",
                                            "enum": ["low", "medium", "high", "critical"],
                                        },
                                        "due_date": {"type": "string"},
                                        "assignee": {"type": "string"},
                                        "notes": {"type": "string"},
                                        "sub_items": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "id": {"type": "string"},
                                                    "text": {"type": "string"},
                                                    "status": {"type": "string"},
                                                },
                                            },
                                        },
                                    },
                                    "required": ["text"],
                                },
                            },
                        },
                        "required": ["name", "items"],
                    },
                },
                "items": {
                    "type": "array",
                    "description": "Flat list of checklist items (alternative to groups).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "text": {"type": "string"},
                            "status": {"type": "string"},
                            "priority": {"type": "string"},
                            "due_date": {"type": "string"},
                            "assignee": {"type": "string"},
                            "notes": {"type": "string"},
                        },
                        "required": ["text"],
                    },
                },
                "include_progress": {
                    "type": "boolean",
                    "description": "Include progress statistics. Defaults to true.",
                },
                "include_legend": {
                    "type": "boolean",
                    "description": "Include status legend. Defaults to true.",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Generating checklist"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Generate a checklist with the specified configuration.

        Args:
            params: Tool parameters including output_path, source, and items.
            context: Execution context.

        Returns:
            Dictionary containing generation status and checklist information.

        Raises:
            FileNotFoundError: If source file doesn't exist.
            ValueError: If checklist configuration is invalid.
            RuntimeError: If checklist generation fails.
        """
        output_path_raw = params.get("output_path")
        write_to_file = isinstance(output_path_raw, str) and output_path_raw.strip()
        output_format = params.get("output_format", "markdown")
        source_type = params.get("source_type", "manual")
        source_path = params.get("source_path")

        if write_to_file:
            output_path = Path(output_path_raw.strip())
            output_path.parent.mkdir(parents=True, exist_ok=True)
            log_output = str(output_path)
        else:
            output_path = None
            log_output = "(inline)"

        logger.info(
            "Generating checklist",
            output_path=log_output,
            format=output_format,
            source=source_type,
        )

        if source_type == "workflow" and source_path:
            checklist_data = self._parse_workflow(source_path)
        elif source_type == "rules" and source_path:
            checklist_data = self._parse_rules(source_path)
        else:
            checklist_data = self._build_manual_checklist(params)

        checklist_data["title"] = params.get("title", checklist_data.get("title", "Checklist"))
        checklist_data["description"] = params.get("description", checklist_data.get("description", ""))
        checklist_data["metadata"] = params.get("metadata", {})
        checklist_data["metadata"]["generated_at"] = datetime.now().isoformat()

        stats = self._calculate_stats(checklist_data)
        checklist_data["stats"] = stats

        if write_to_file and output_path is not None:
            if output_format == "markdown":
                self._export_markdown(output_path, checklist_data, params)
            elif output_format == "json":
                self._export_json(output_path, checklist_data)
            elif output_format == "html":
                self._export_html(output_path, checklist_data, params)
            elif output_format == "pdf":
                self._export_pdf(output_path, checklist_data, params)
            else:
                raise ValueError(f"Unsupported output format: {output_format}")

            file_size = output_path.stat().st_size
            logger.info(
                "Checklist generated successfully",
                output_path=str(output_path),
                file_size=file_size,
                **stats,
            )
            return {
                "success": True,
                "output_path": str(output_path),
                "output_format": output_format,
                "file_size_bytes": file_size,
                "stats": stats,
                "title": checklist_data["title"],
            }

        inline_content: str | None = None
        if output_format == "markdown":
            inline_content = self._build_markdown_content(checklist_data, params)
        elif output_format == "json":
            inline_content = json.dumps(checklist_data, indent=2, ensure_ascii=False)
        elif output_format == "html":
            inline_content = self._build_html_content(checklist_data, params)
        elif output_format == "pdf":
            raise ValueError("PDF export requires output_path; inline PDF is not supported")
        else:
            raise ValueError(f"Unsupported output format: {output_format}")

        logger.info("Checklist generated inline", format=output_format, **stats)
        return {
            "success": True,
            "output_format": output_format,
            "content": inline_content,
            "stats": stats,
            "title": checklist_data["title"],
        }

    def _parse_workflow(self, source_path: str) -> dict[str, Any]:
        """Parse workflow file to extract checklist items."""
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Workflow file not found: {source_path}")

        content = path.read_text(encoding="utf-8")

        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml
                data = yaml.safe_load(content)
            except ImportError:
                raise RuntimeError("PyYAML is not installed. Install with: pip install pyyaml")
        elif path.suffix == ".json":
            data = json.loads(content)
        else:
            raise ValueError(f"Unsupported workflow file format: {path.suffix}")

        checklist: dict[str, Any] = {
            "title": data.get("name", data.get("workflow", {}).get("name", "Workflow Checklist")),
            "description": data.get("description", ""),
            "groups": [],
        }

        steps = data.get("steps", data.get("workflow", {}).get("steps", []))
        if steps:
            step_items = []
            for i, step in enumerate(steps):
                if isinstance(step, dict):
                    item = {
                        "id": step.get("id", f"step_{i+1}"),
                        "text": step.get("name", step.get("description", f"Step {i+1}")),
                        "status": "pending",
                        "notes": step.get("description", ""),
                    }

                    if step.get("actions"):
                        item["sub_items"] = [
                            {"id": f"{item['id']}_action_{j}", "text": str(action), "status": "pending"}
                            for j, action in enumerate(step["actions"])
                        ]

                    step_items.append(item)
                elif isinstance(step, str):
                    step_items.append({
                        "id": f"step_{i+1}",
                        "text": step,
                        "status": "pending",
                    })

            checklist["groups"].append({
                "name": "Workflow Steps",
                "items": step_items,
            })

        validations = data.get("validations", data.get("workflow", {}).get("validations", []))
        if validations:
            validation_items = []
            for i, val in enumerate(validations):
                if isinstance(val, dict):
                    validation_items.append({
                        "id": f"validation_{i+1}",
                        "text": val.get("name", val.get("rule", f"Validation {i+1}")),
                        "status": "pending",
                    })
                elif isinstance(val, str):
                    validation_items.append({
                        "id": f"validation_{i+1}",
                        "text": val,
                        "status": "pending",
                    })

            if validation_items:
                checklist["groups"].append({
                    "name": "Validations",
                    "items": validation_items,
                })

        return checklist

    def _parse_rules(self, source_path: str) -> dict[str, Any]:
        """Parse rules file to extract checklist items."""
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Rules file not found: {source_path}")

        content = path.read_text(encoding="utf-8")

        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml
                data = yaml.safe_load(content)
            except ImportError:
                raise RuntimeError("PyYAML is not installed. Install with: pip install pyyaml")
        elif path.suffix == ".json":
            data = json.loads(content)
        else:
            raise ValueError(f"Unsupported rules file format: {path.suffix}")

        checklist: dict[str, Any] = {
            "title": data.get("name", "Compliance Checklist"),
            "description": data.get("description", ""),
            "groups": [],
        }

        rules = data.get("rules", data.get("items", []))
        if isinstance(rules, list):
            rule_items = []
            for i, rule in enumerate(rules):
                if isinstance(rule, dict):
                    priority = rule.get("severity", rule.get("priority", "medium"))
                    if priority in ("error", "critical"):
                        priority = "critical"
                    elif priority == "warning":
                        priority = "high"
                    else:
                        priority = "medium"

                    rule_items.append({
                        "id": rule.get("id", f"rule_{i+1}"),
                        "text": rule.get("name", rule.get("description", f"Rule {i+1}")),
                        "status": "pending",
                        "priority": priority,
                        "notes": rule.get("description", rule.get("message", "")),
                    })
                elif isinstance(rule, str):
                    rule_items.append({
                        "id": f"rule_{i+1}",
                        "text": rule,
                        "status": "pending",
                        "priority": "medium",
                    })

            checklist["groups"].append({
                "name": "Compliance Rules",
                "items": rule_items,
            })

        elif isinstance(rules, dict):
            for category, category_rules in rules.items():
                if isinstance(category_rules, list):
                    group_items = []
                    for i, rule in enumerate(category_rules):
                        if isinstance(rule, dict):
                            group_items.append({
                                "id": rule.get("id", f"{category}_{i+1}"),
                                "text": rule.get("name", rule.get("description", f"Rule {i+1}")),
                                "status": "pending",
                                "priority": rule.get("priority", "medium"),
                            })
                        elif isinstance(rule, str):
                            group_items.append({
                                "id": f"{category}_{i+1}",
                                "text": rule,
                                "status": "pending",
                            })

                    checklist["groups"].append({
                        "name": category.replace("_", " ").title(),
                        "items": group_items,
                    })

        return checklist

    def _build_manual_checklist(self, params: dict[str, Any]) -> dict[str, Any]:
        """Build checklist from manual input."""
        checklist: dict[str, Any] = {
            "title": params.get("title", "Checklist"),
            "description": params.get("description", ""),
            "groups": [],
        }

        groups = params.get("groups", [])
        if groups:
            for group in groups:
                processed_items = []
                for i, item in enumerate(group.get("items", [])):
                    processed_item = {
                        "id": item.get("id", f"item_{i+1}"),
                        "text": item.get("text", ""),
                        "status": item.get("status", "pending"),
                        "priority": item.get("priority"),
                        "due_date": item.get("due_date"),
                        "assignee": item.get("assignee"),
                        "notes": item.get("notes"),
                    }

                    if item.get("sub_items"):
                        processed_item["sub_items"] = [
                            {
                                "id": si.get("id", f"{processed_item['id']}_sub_{j}"),
                                "text": si.get("text", ""),
                                "status": si.get("status", "pending"),
                            }
                            for j, si in enumerate(item["sub_items"])
                        ]

                    processed_items.append(processed_item)

                checklist["groups"].append({
                    "name": group.get("name", f"Group {len(checklist['groups']) + 1}"),
                    "description": group.get("description", ""),
                    "items": processed_items,
                })

        items = params.get("items", [])
        if items and not groups:
            processed_items = []
            for i, item in enumerate(items):
                processed_items.append({
                    "id": item.get("id", f"item_{i+1}"),
                    "text": item.get("text", ""),
                    "status": item.get("status", "pending"),
                    "priority": item.get("priority"),
                    "due_date": item.get("due_date"),
                    "assignee": item.get("assignee"),
                    "notes": item.get("notes"),
                })

            checklist["groups"].append({
                "name": "Items",
                "items": processed_items,
            })

        return checklist

    def _calculate_stats(self, checklist: dict[str, Any]) -> dict[str, Any]:
        """Calculate checklist statistics."""
        total = 0
        completed = 0
        in_progress = 0
        blocked = 0
        by_priority: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for group in checklist.get("groups", []):
            for item in group.get("items", []):
                total += 1
                status = item.get("status", "pending")

                if status == "completed":
                    completed += 1
                elif status == "in_progress":
                    in_progress += 1
                elif status == "blocked":
                    blocked += 1

                priority = item.get("priority", "medium")
                if priority in by_priority:
                    by_priority[priority] += 1

                for sub_item in item.get("sub_items", []):
                    total += 1
                    if sub_item.get("status") == "completed":
                        completed += 1

        progress_pct = round((completed / total * 100), 1) if total > 0 else 0

        return {
            "total_items": total,
            "completed": completed,
            "in_progress": in_progress,
            "blocked": blocked,
            "pending": total - completed - in_progress - blocked,
            "progress_percentage": progress_pct,
            "by_priority": by_priority,
        }

    def _build_markdown_content(
        self,
        checklist: dict[str, Any],
        params: dict[str, Any],
    ) -> str:
        """Build checklist Markdown without writing to disk."""
        lines: list[str] = []

        lines.append(f"# {checklist['title']}")
        if checklist.get("description"):
            lines.append(f"\n{checklist['description']}")
        lines.append("")

        if params.get("include_progress", True):
            stats = checklist.get("stats", {})
            lines.append("## Progress")
            lines.append(f"\n**{stats.get('progress_percentage', 0)}%** complete "
                        f"({stats.get('completed', 0)}/{stats.get('total_items', 0)} items)")
            lines.append(f"- Completed: {stats.get('completed', 0)}")
            lines.append(f"- In Progress: {stats.get('in_progress', 0)}")
            lines.append(f"- Blocked: {stats.get('blocked', 0)}")
            lines.append(f"- Pending: {stats.get('pending', 0)}")
            lines.append("")

        status_symbols = {
            "completed": "[x]",
            "in_progress": "[-]",
            "blocked": "[!]",
            "skipped": "[~]",
            "pending": "[ ]",
        }

        priority_symbols = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }

        for group in checklist.get("groups", []):
            lines.append(f"## {group['name']}")
            if group.get("description"):
                lines.append(f"\n{group['description']}")
            lines.append("")

            for item in group.get("items", []):
                status = item.get("status", "pending")
                symbol = status_symbols.get(status, "[ ]")
                priority = item.get("priority")
                priority_indicator = priority_symbols.get(priority, "") if priority else ""

                line = f"- {symbol} {priority_indicator}{item['text']}"

                if item.get("assignee"):
                    line += f" @{item['assignee']}"
                if item.get("due_date"):
                    line += f" (due: {item['due_date']})"

                lines.append(line)

                if item.get("notes"):
                    lines.append(f"  - *{item['notes']}*")

                for sub_item in item.get("sub_items", []):
                    sub_status = sub_item.get("status", "pending")
                    sub_symbol = status_symbols.get(sub_status, "[ ]")
                    lines.append(f"  - {sub_symbol} {sub_item['text']}")

            lines.append("")

        if params.get("include_legend", True):
            lines.append("---")
            lines.append("### Legend")
            lines.append("- `[x]` Completed")
            lines.append("- `[-]` In Progress")
            lines.append("- `[!]` Blocked")
            lines.append("- `[~]` Skipped")
            lines.append("- `[ ]` Pending")
            lines.append("")

        return "\n".join(lines)

    def _export_markdown(
        self,
        output_path: Path,
        checklist: dict[str, Any],
        params: dict[str, Any],
    ) -> None:
        """Export checklist to Markdown format."""
        output_path.write_text(
            self._build_markdown_content(checklist, params),
            encoding="utf-8",
        )

    def _export_json(self, output_path: Path, checklist: dict[str, Any]) -> None:
        """Export checklist to JSON format."""
        output_path.write_text(json.dumps(checklist, indent=2, ensure_ascii=False), encoding="utf-8")

    def _build_html_content(
        self,
        checklist: dict[str, Any],
        params: dict[str, Any],
    ) -> str:
        """Build checklist HTML without writing to disk."""
        stats = checklist.get("stats", {})

        status_colors = {
            "completed": "#38a169",
            "in_progress": "#3182ce",
            "blocked": "#e53e3e",
            "skipped": "#718096",
            "pending": "#a0aec0",
        }

        priority_colors = {
            "critical": "#e53e3e",
            "high": "#ed8936",
            "medium": "#ecc94b",
            "low": "#48bb78",
        }

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{checklist['title']}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f7fafc; }}
        h1 {{ color: #2d3748; border-bottom: 3px solid #4299e1; padding-bottom: 10px; }}
        h2 {{ color: #4a5568; margin-top: 30px; }}
        .description {{ color: #718096; margin-bottom: 20px; }}
        .progress-container {{ background: #e2e8f0; border-radius: 10px; overflow: hidden; margin: 20px 0; }}
        .progress-bar {{ background: #48bb78; height: 24px; text-align: center; color: white; font-weight: bold; line-height: 24px; transition: width 0.3s; }}
        .stats {{ display: flex; gap: 20px; flex-wrap: wrap; margin: 20px 0; }}
        .stat {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 100px; text-align: center; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #2d3748; }}
        .stat-label {{ font-size: 12px; color: #718096; text-transform: uppercase; }}
        .group {{ background: white; border-radius: 8px; padding: 20px; margin: 20px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .item {{ display: flex; align-items: flex-start; padding: 10px 0; border-bottom: 1px solid #e2e8f0; }}
        .item:last-child {{ border-bottom: none; }}
        .checkbox {{ width: 20px; height: 20px; border-radius: 4px; margin-right: 12px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; color: white; font-size: 12px; }}
        .item-content {{ flex: 1; }}
        .item-text {{ font-size: 14px; color: #2d3748; }}
        .item-meta {{ font-size: 12px; color: #718096; margin-top: 4px; }}
        .priority {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; color: white; margin-left: 8px; }}
        .sub-items {{ margin-left: 32px; margin-top: 8px; }}
        .sub-item {{ display: flex; align-items: center; padding: 4px 0; font-size: 13px; color: #4a5568; }}
        .legend {{ margin-top: 30px; padding: 15px; background: #edf2f7; border-radius: 8px; }}
        .legend-item {{ display: inline-flex; align-items: center; margin-right: 20px; font-size: 13px; }}
        .legend-box {{ width: 16px; height: 16px; border-radius: 3px; margin-right: 6px; }}
    </style>
</head>
<body>
    <h1>{checklist['title']}</h1>
    {"<p class='description'>" + checklist['description'] + "</p>" if checklist.get('description') else ""}
"""

        if params.get("include_progress", True):
            html += f"""
    <div class="progress-container">
        <div class="progress-bar" style="width: {stats.get('progress_percentage', 0)}%">{stats.get('progress_percentage', 0)}%</div>
    </div>
    <div class="stats">
        <div class="stat"><div class="stat-value">{stats.get('total_items', 0)}</div><div class="stat-label">Total</div></div>
        <div class="stat"><div class="stat-value" style="color: #38a169">{stats.get('completed', 0)}</div><div class="stat-label">Completed</div></div>
        <div class="stat"><div class="stat-value" style="color: #3182ce">{stats.get('in_progress', 0)}</div><div class="stat-label">In Progress</div></div>
        <div class="stat"><div class="stat-value" style="color: #e53e3e">{stats.get('blocked', 0)}</div><div class="stat-label">Blocked</div></div>
    </div>
"""

        for group in checklist.get("groups", []):
            html += f"""
    <div class="group">
        <h2>{group['name']}</h2>
        {"<p class='description'>" + group['description'] + "</p>" if group.get('description') else ""}
"""
            for item in group.get("items", []):
                status = item.get("status", "pending")
                color = status_colors.get(status, "#a0aec0")
                check = "✓" if status == "completed" else ("−" if status == "in_progress" else ("!" if status == "blocked" else ""))

                priority_html = ""
                if item.get("priority"):
                    p_color = priority_colors.get(item["priority"], "#ecc94b")
                    priority_html = f"<span class='priority' style='background: {p_color}'>{item['priority'].upper()}</span>"

                meta_parts = []
                if item.get("assignee"):
                    meta_parts.append(f"@{item['assignee']}")
                if item.get("due_date"):
                    meta_parts.append(f"Due: {item['due_date']}")
                meta_html = f"<div class='item-meta'>{' | '.join(meta_parts)}</div>" if meta_parts else ""

                html += f"""
        <div class="item">
            <div class="checkbox" style="background: {color}">{check}</div>
            <div class="item-content">
                <div class="item-text">{item['text']}{priority_html}</div>
                {meta_html}
"""
                if item.get("sub_items"):
                    html += "<div class='sub-items'>"
                    for sub in item["sub_items"]:
                        sub_status = sub.get("status", "pending")
                        sub_check = "✓" if sub_status == "completed" else "○"
                        html += f"<div class='sub-item'><span style='margin-right: 8px'>{sub_check}</span>{sub['text']}</div>"
                    html += "</div>"

                html += """
            </div>
        </div>
"""
            html += "</div>"

        if params.get("include_legend", True):
            html += """
    <div class="legend">
        <strong>Legend:</strong>
        <div class="legend-item"><div class="legend-box" style="background: #38a169"></div>Completed</div>
        <div class="legend-item"><div class="legend-box" style="background: #3182ce"></div>In Progress</div>
        <div class="legend-item"><div class="legend-box" style="background: #e53e3e"></div>Blocked</div>
        <div class="legend-item"><div class="legend-box" style="background: #a0aec0"></div>Pending</div>
    </div>
"""

        html += """
</body>
</html>
"""
        return html

    def _export_html(
        self,
        output_path: Path,
        checklist: dict[str, Any],
        params: dict[str, Any],
    ) -> None:
        """Export checklist to HTML format."""
        output_path.write_text(
            self._build_html_content(checklist, params),
            encoding="utf-8",
        )

    def _export_pdf(
        self,
        output_path: Path,
        checklist: dict[str, Any],
        params: dict[str, Any],
    ) -> None:
        """Export checklist to PDF format."""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except ImportError as e:
            raise RuntimeError(
                "reportlab is not installed. Install with: pip install reportlab"
            ) from e

        doc = SimpleDocTemplate(str(output_path), pagesize=A4)
        styles = getSampleStyleSheet()
        story: list[Any] = []

        story.append(Paragraph(checklist["title"], styles["Title"]))
        if checklist.get("description"):
            story.append(Paragraph(checklist["description"], styles["Normal"]))
        story.append(Spacer(1, 20))

        if params.get("include_progress", True):
            stats = checklist.get("stats", {})
            progress_text = (
                f"Progress: {stats.get('progress_percentage', 0)}% complete "
                f"({stats.get('completed', 0)}/{stats.get('total_items', 0)} items)"
            )
            story.append(Paragraph(progress_text, styles["Heading2"]))
            story.append(Spacer(1, 10))

        status_symbols = {
            "completed": "✓",
            "in_progress": "○",
            "blocked": "✗",
            "skipped": "−",
            "pending": "□",
        }

        for group in checklist.get("groups", []):
            story.append(Paragraph(group["name"], styles["Heading2"]))
            story.append(Spacer(1, 10))

            table_data = [["Status", "Item", "Priority", "Assignee"]]

            for item in group.get("items", []):
                status = item.get("status", "pending")
                symbol = status_symbols.get(status, "□")
                priority = item.get("priority", "-")
                assignee = item.get("assignee", "-")

                table_data.append([symbol, item["text"][:50], priority, assignee])

            table = Table(table_data, colWidths=[50, 280, 70, 80])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.2, 0.4, 0.6)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ]))

            story.append(table)
            story.append(Spacer(1, 20))

        doc.build(story)
