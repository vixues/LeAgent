"""Round-trip serialization helpers for ``WorkflowDocument``."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .loader import WorkflowDocument


def to_json(doc: WorkflowDocument, *, indent: int | None = 2) -> str:
    return json.dumps(doc.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)


def to_yaml(doc: WorkflowDocument) -> str:
    return yaml.safe_dump(doc.to_dict(), sort_keys=False, allow_unicode=True)


def save(doc: WorkflowDocument, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.suffix in (".yaml", ".yml"):
        p.write_text(to_yaml(doc), encoding="utf-8")
    else:
        p.write_text(to_json(doc), encoding="utf-8")


def graph_hash(doc: WorkflowDocument) -> str:
    """Stable hash of the document graph used as a cache key salt."""
    canonical = json.dumps(
        {
            "nodes": doc.nodes,
            "control": doc.control,
            "inputs": doc.inputs,
            "outputs": doc.outputs,
        },
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def export(doc: WorkflowDocument) -> dict[str, Any]:
    """Export a document as a plain canonical ``dict``."""
    return doc.to_dict()
