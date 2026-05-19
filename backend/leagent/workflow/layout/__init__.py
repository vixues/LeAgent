"""Deterministic graph layout for workflow documents.

This package is the single source of truth for computing `(x, y)` node
coordinates on the backend. It is consumed by two callers:

* :mod:`leagent.api.v1.templates` — pre-layouts every flow that is
  instantiated from a template, so the editor canvas renders a clean
  left-to-right topology the first time it opens.
* :mod:`scripts.workflow.migrate_flows` — backfills positions for
  existing ``Flow.data`` rows via the ``--relayout`` flag.

Both ``extract_edges`` and ``compute_layout`` are pure functions over a
canonical ``WorkflowDocument``-shaped dict (see
:mod:`leagent.workflow.io.loader`). They do not touch the database,
ReactFlow, or any UI framework.

The combined helper :func:`layout_document` returns the canonical
document with a sibling ``ui`` block attached::

    {
      "id": ..., "name": ..., ..., "nodes": {...}, "control": {...},
      "ui": {
        "nodes": [ {id, type: "generic", position: {x, y}, data: {...}} ],
        "edges": [ {id, source, target, label, type} ]
      }
    }

The ``ui`` block is the fast-path the frontend consumes — the rest of
the document remains canonical so the engine can still ``load()`` it
without any migration step.
"""

from __future__ import annotations

from .edges import LayoutEdge, extract_edges
from .engine import LayoutOptions, compute_layout
from .ui import build_ui_block, layout_document

__all__ = [
    "LayoutEdge",
    "LayoutOptions",
    "build_ui_block",
    "compute_layout",
    "extract_edges",
    "layout_document",
]
