"""Load + parse workflow documents.

The engine operates on a single canonical document shape::

    {
      "id": "...",
      "name": "...",
      "description": "...",
      "inputs":  [...],
      "outputs": [...],
      "metadata": {...},
      "nodes": {
        "<node_id>": {
          "class_type": "ToolCallNode",
          "inputs": {...},
          "meta": {...},
          "control": {"next": "...", "conditions": [...], ...}
        }, ...
      },
      "control": {"start": "...", "end": "...", "edges": [...]}
    }

``load()`` accepts that shape only. Anything else raises
:class:`WorkflowLoaderError` — there is no runtime migration path.
Historical payloads have been converted once via
``scripts/workflow/migrate_flows.py`` and the enterprise YAML/JSON
templates are authored in the canonical shape directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class WorkflowLoaderError(Exception):
    """Raised when a document cannot be parsed into a ``WorkflowDocument``."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


@dataclass
class WorkflowDocument:
    """Canonical in-memory representation of a workflow document.

    See the module docstring for the on-disk shape. The engine only ever
    sees this type — no legacy flavours leak past :func:`load`.
    """

    id: str
    name: str
    description: str
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    control: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "WorkflowDocument":
        _assert_canonical(raw)
        return cls(
            id=str(raw.get("id", "") or ""),
            name=str(raw.get("name", "Unnamed Workflow") or "Unnamed Workflow"),
            description=str(raw.get("description", "") or ""),
            inputs=list(raw.get("inputs", []) or []),
            outputs=list(raw.get("outputs", []) or []),
            metadata=dict(raw.get("metadata", {}) or {}),
            nodes=dict(raw.get("nodes", {}) or {}),
            control=dict(raw.get("control", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "metadata": dict(self.metadata),
            "nodes": dict(self.nodes),
            "control": dict(self.control),
        }

    @property
    def start_id(self) -> str:
        return self.control.get("start", "start")

    @property
    def end_id(self) -> str:
        return self.control.get("end", "end")

    @property
    def edges(self) -> list[dict[str, Any]]:
        return list(self.control.get("edges", []) or [])


def _assert_canonical(raw: dict[str, Any]) -> None:
    """Reject anything that is not the canonical shape.

    A canonical document is a mapping with:
    - ``nodes`` as a ``dict[node_id, node_spec]`` (not a list).
    - Each ``node_spec`` carries at minimum a ``class_type`` string.
    - ``control`` as a mapping (may be empty for single-node workflows).

    Legacy payloads (``nodes`` as a list + ``edges`` sibling) are not
    accepted. Run ``scripts/workflow/migrate_flows.py`` once to upgrade.
    """
    if not isinstance(raw, dict):
        raise WorkflowLoaderError(
            f"Workflow document must be a mapping, got {type(raw).__name__}"
        )

    nodes = raw.get("nodes")
    if not isinstance(nodes, dict):
        raise WorkflowLoaderError(
            "Workflow document is not in the canonical shape: "
            "'nodes' must be a mapping of node_id -> {class_type, inputs, meta, control}."
            " Run scripts/workflow/migrate_flows.py to upgrade legacy payloads."
        )

    for node_id, spec in nodes.items():
        if not isinstance(spec, dict):
            raise WorkflowLoaderError(
                f"Node '{node_id}' must be a mapping, got {type(spec).__name__}"
            )
        if not spec.get("class_type"):
            raise WorkflowLoaderError(
                f"Node '{node_id}' is missing required 'class_type' field"
            )

    control = raw.get("control", {})
    if control is not None and not isinstance(control, dict):
        raise WorkflowLoaderError(
            f"'control' must be a mapping, got {type(control).__name__}"
        )


def load(source: str | Path | dict[str, Any]) -> WorkflowDocument:
    """Load a workflow document from a file path, string, or dict."""
    if isinstance(source, dict):
        return WorkflowDocument.from_dict(source)
    if isinstance(source, Path):
        return _load_file(source)
    text = str(source)
    if text.endswith((".yaml", ".yml", ".json")) and Path(text).exists():
        return _load_file(Path(text))
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return WorkflowDocument.from_dict(json.loads(stripped))
        except json.JSONDecodeError as e:
            raise WorkflowLoaderError(f"Invalid JSON: {e}") from e
    try:
        data = yaml.safe_load(stripped)
    except yaml.YAMLError as e:
        raise WorkflowLoaderError(f"Invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise WorkflowLoaderError("Workflow document must be a mapping")
    return WorkflowDocument.from_dict(data)


def _load_file(path: Path) -> WorkflowDocument:
    if not path.exists():
        raise WorkflowLoaderError(f"Workflow file not found: {path}")
    content = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise WorkflowLoaderError(f"Invalid YAML: {e}") from e
    elif path.suffix == ".json":
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise WorkflowLoaderError(f"Invalid JSON: {e}") from e
    else:
        try:
            data = yaml.safe_load(content)
        except Exception:
            data = json.loads(content)
    if not isinstance(data, dict):
        raise WorkflowLoaderError("Workflow document must be a mapping")
    return WorkflowDocument.from_dict(data)
