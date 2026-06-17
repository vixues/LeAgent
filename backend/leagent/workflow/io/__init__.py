"""Independent IO module for the workflow engine.

Owns everything that sits between the persisted workflow document and
the executor: typed primitives, schema metadata, loader, validator, and
serialization. Nothing in this package imports from ``engine``,
``nodes``, ``queue``, or ``server`` — keep it leaf-level so the
frontend and CLI can parse documents without booting the runtime.

Single canonical schema — no version migration layer. Historical
payloads were upgraded once via
``scripts/workflow/migrate_flows.py``.
"""

from __future__ import annotations

from .hidden import Hidden, HiddenHolder
from .loader import WorkflowDocument, WorkflowLoaderError, load
from .media import MediaRef, to_gen_ui_tree
from .node_output import NodeOutput
from .schema import Schema
from .schema_bridge import json_schema_to_inputs
from .serializer import export, graph_hash, save, to_json, to_yaml
from .contract import Contract, default_check_lazy_status, default_fingerprint_inputs
from .types import (
    IO,
    Input,
    InputBase,
    OutputBase,
    WidgetInput,
    WILDCARD_TYPE,
    all_socket_colors,
    socket_color,
    types_compatible,
    widget_kind,
)
from .validator import validate

__all__ = [
    "Contract",
    "Hidden",
    "HiddenHolder",
    "IO",
    "Input",
    "InputBase",
    "MediaRef",
    "NodeOutput",
    "OutputBase",
    "Schema",
    "to_gen_ui_tree",
    "WidgetInput",
    "WILDCARD_TYPE",
    "WorkflowDocument",
    "WorkflowLoaderError",
    "all_socket_colors",
    "default_check_lazy_status",
    "default_fingerprint_inputs",
    "export",
    "graph_hash",
    "json_schema_to_inputs",
    "load",
    "save",
    "socket_color",
    "to_json",
    "to_yaml",
    "types_compatible",
    "validate",
    "widget_kind",
]
