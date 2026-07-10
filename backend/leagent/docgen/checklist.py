"""Shared checklist logic: status/priority styling, stats, source adapters.

Format-agnostic helpers used by every renderer (PDF/DOCX/HTML/Markdown) and
by the ``checklist_generate`` tool, so a checklist looks and counts the same
everywhere. This restores — and generalises — the capabilities of the legacy
``checklist_generator`` tool inside the unified ``docgen`` subsystem.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from leagent.docgen.model import ChecklistBlock, ChecklistItem

logger = structlog.get_logger(__name__)


# Status → (glyph, hex color, human label). Glyphs are chosen to render with
# the bundled Noto fonts in every backend.
STATUS_META: dict[str, tuple[str, str, str]] = {
    "completed": ("✓", "#2F9E5B", "Completed"),
    "in_progress": ("◐", "#2F6FB0", "In progress"),
    "blocked": ("✕", "#C0392B", "Blocked"),
    "skipped": ("–", "#8A8F98", "Skipped"),
    "pending": ("☐", "#A0A4AB", "Pending"),
}

PRIORITY_META: dict[str, tuple[str, str]] = {
    "critical": ("#C0392B", "Critical"),
    "high": ("#E08600", "High"),
    "medium": ("#B8860B", "Medium"),
    "low": ("#2F9E5B", "Low"),
}

# Localised progress/legend labels (mirrors the docgen zh/en split).
LABELS = {
    "en": {
        "progress": "Progress",
        "complete": "complete",
        "items": "items",
        "total": "Total",
        "legend": "Legend",
        "notes": "Notes",
        "due": "Due",
    },
    "zh": {
        "progress": "进度",
        "complete": "完成",
        "items": "项",
        "total": "总计",
        "legend": "图例",
        "notes": "备注",
        "due": "截止",
    },
}


def status_meta(status: str) -> tuple[str, str, str]:
    return STATUS_META.get(status, STATUS_META["pending"])


def priority_meta(priority: str | None) -> tuple[str, str] | None:
    if not priority:
        return None
    return PRIORITY_META.get(priority)


def checklist_stats(block: ChecklistBlock) -> dict[str, Any]:
    """Count items by status (including nested sub-items) and progress %."""
    counts = {k: 0 for k in STATUS_META}
    total = 0

    def _walk(items: list[ChecklistItem]) -> None:
        nonlocal total
        for item in items:
            total += 1
            counts[item.status] = counts.get(item.status, 0) + 1
            if item.sub_items:
                _walk(item.sub_items)

    for group in block.normalized_groups():
        _walk(group.items)

    completed = counts.get("completed", 0)
    # Skipped items don't count against completion.
    effective = total - counts.get("skipped", 0)
    pct = round(completed / effective * 100) if effective else 0
    return {
        "total_items": total,
        "progress_percentage": pct,
        **counts,
    }


def checklist_to_dict(block: ChecklistBlock) -> dict[str, Any]:
    """Serialise a checklist to a plain dict (JSON export parity)."""
    data = block.model_dump(exclude_none=True, exclude_defaults=False)
    data["groups"] = [
        g.model_dump(exclude_none=True) for g in block.normalized_groups()
    ]
    data.pop("items", None)
    data["stats"] = checklist_stats(block)
    return data


# ---------------------------------------------------------------------------
# Source adapters (workflow / rules → checklist)
# ---------------------------------------------------------------------------


def _load_structured(path: str | Path) -> Any:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        import yaml

        return yaml.safe_load(text)
    if p.suffix.lower() == ".json":
        return json.loads(text)
    # Try JSON then YAML.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import yaml

        return yaml.safe_load(text)


def parse_workflow_checklist(path: str | Path) -> ChecklistBlock:
    """Build a checklist from a workflow definition (nodes → items).

    Recognises common workflow shapes: a ``nodes``/``steps`` list (each with
    ``id``/``name``/``label``/``title`` and optional ``description``). Node
    order becomes item order; nothing is assumed about status (all pending).
    """
    data = _load_structured(path) or {}
    title = data.get("name") or data.get("title") or Path(path).stem
    description = data.get("description")
    nodes = data.get("nodes") or data.get("steps") or data.get("tasks") or []
    items: list[ChecklistItem] = []
    for node in nodes:
        if not isinstance(node, dict):
            items.append(ChecklistItem(text=str(node)))
            continue
        text = (
            node.get("label")
            or node.get("name")
            or node.get("title")
            or node.get("id")
            or "Step"
        )
        items.append(
            ChecklistItem(
                id=str(node.get("id")) if node.get("id") is not None else None,
                text=str(text),
                notes=node.get("description") or node.get("note"),
            )
        )
    return ChecklistBlock(title=str(title), description=description, items=items)


def parse_rules_checklist(path: str | Path) -> ChecklistBlock:
    """Build a checklist from a rules file (each rule → a checklist item)."""
    data = _load_structured(path) or {}
    if isinstance(data, list):
        rules = data
        title = Path(path).stem
        description = None
    else:
        rules = data.get("rules") or data.get("items") or []
        title = data.get("name") or data.get("title") or Path(path).stem
        description = data.get("description")
    items: list[ChecklistItem] = []
    for rule in rules:
        if not isinstance(rule, dict):
            items.append(ChecklistItem(text=str(rule)))
            continue
        text = (
            rule.get("description")
            or rule.get("name")
            or rule.get("title")
            or rule.get("id")
            or "Rule"
        )
        items.append(
            ChecklistItem(
                id=str(rule.get("id")) if rule.get("id") is not None else None,
                text=str(text),
                priority=rule.get("priority")
                if rule.get("priority") in PRIORITY_META
                else None,
            )
        )
    return ChecklistBlock(title=str(title), description=description, items=items)


def build_checklist_block(params: dict[str, Any]) -> ChecklistBlock:
    """Build a :class:`ChecklistBlock` from tool params (manual/workflow/rules)."""
    source_type = params.get("source_type", "manual")
    source_path = params.get("source_path")
    if source_type == "workflow" and source_path:
        block = parse_workflow_checklist(source_path)
    elif source_type == "rules" and source_path:
        block = parse_rules_checklist(source_path)
    else:
        block = ChecklistBlock.model_validate(
            {
                "groups": params.get("groups", []),
                "items": params.get("items", []),
            }
        )
    if params.get("title"):
        block.title = params["title"]
    if params.get("description"):
        block.description = params["description"]
    if "include_progress" in params:
        block.show_progress = bool(params["include_progress"])
    if "include_legend" in params:
        block.show_legend = bool(params["include_legend"])
    return block
