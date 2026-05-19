"""Bridge from JSON Schema (tool parameter schemas) to typed IO inputs.

Every :class:`~leagent.tools.base.BaseTool` advertises its parameters as a
JSON Schema ``{"type": "object", "properties": {...}, "required": [...]}``.
The workflow editor, in contrast, consumes typed :class:`IO.*.Input`
descriptors to render widgets and validate links. This module performs the
one-way translation at node-class build time so every registered tool can
appear as a distinct workflow palette entry with correctly typed sockets.

Mapping rules (best-effort; unknown shapes fall back to ``IO.Any.Input``):

- ``{"type": "string", "enum": [...]}`` → :class:`IO.Combo.Input`
- ``{"type": "string"}``                → :class:`IO.String.Input`
  - honours ``default``, ``description``, ``pattern``, ``minLength``,
    ``maxLength``, and treats ``description`` containing newlines or
    ``"multiline": true`` as multiline.
- ``{"type": "integer"}``               → :class:`IO.Int.Input`
  - honours ``minimum``, ``maximum``, ``multipleOf``, ``default``.
- ``{"type": "number"}``                → :class:`IO.Float.Input`.
- ``{"type": "boolean"}``               → :class:`IO.Boolean.Input`.
- ``{"type": "array"}``                 → :class:`IO.Array.Input`.
- ``{"type": "object"}``                → :class:`IO.Object.Input`.
- ``oneOf`` / ``anyOf`` / missing type  → :class:`IO.Any.Input`.

The bridge never raises on malformed schemas — tools that ship exotic
schemas just degrade to wildcard ``Any`` inputs so the workflow still
loads. This is intentional: tool authors must not be able to brick the
editor with a typo.
"""

from __future__ import annotations

from typing import Any

from .types import IO, InputBase


def _resolve_type(prop: dict[str, Any]) -> str | None:
    """Resolve a single canonical JSON Schema type, or None if ambiguous."""
    t = prop.get("type")
    if isinstance(t, list):
        non_null = [x for x in t if x != "null"]
        if len(non_null) == 1:
            return non_null[0]
        return None
    if isinstance(t, str):
        return t
    return None


def _build_input(
    prop_id: str,
    prop_schema: dict[str, Any],
    *,
    required: bool,
) -> InputBase:
    """Convert one JSON Schema property → the richest matching IO input."""
    description = prop_schema.get("description") or None
    default = prop_schema.get("default")
    optional = not required

    enum = prop_schema.get("enum")
    if isinstance(enum, list) and enum:
        return IO.Combo.Input(
            id=prop_id,
            tooltip=description,
            optional=optional,
            default=default,
            choices=[str(v) for v in enum],
        )

    jstype = _resolve_type(prop_schema)

    if jstype == "string":
        multiline = bool(prop_schema.get("multiline"))
        if description and "\n" in description:
            multiline = True
        return IO.String.Input(
            id=prop_id,
            tooltip=description,
            optional=optional,
            default=default if isinstance(default, str) else (default if default is None else str(default)),
            multiline=multiline,
            pattern=prop_schema.get("pattern"),
            min_length=prop_schema.get("minLength"),
            max_length=prop_schema.get("maxLength"),
        )

    if jstype == "integer":
        step = int(prop_schema.get("multipleOf", 1)) if isinstance(prop_schema.get("multipleOf"), (int, float)) else 1
        return IO.Int.Input(
            id=prop_id,
            tooltip=description,
            optional=optional,
            default=default if isinstance(default, int) and not isinstance(default, bool) else default,
            min=prop_schema.get("minimum"),
            max=prop_schema.get("maximum"),
            step=max(1, step),
        )

    if jstype == "number":
        step_raw = prop_schema.get("multipleOf", 0.01)
        step = float(step_raw) if isinstance(step_raw, (int, float)) else 0.01
        return IO.Float.Input(
            id=prop_id,
            tooltip=description,
            optional=optional,
            default=default if isinstance(default, (int, float)) and not isinstance(default, bool) else default,
            min=prop_schema.get("minimum"),
            max=prop_schema.get("maximum"),
            step=step,
        )

    if jstype == "boolean":
        return IO.Boolean.Input(
            id=prop_id,
            tooltip=description,
            optional=optional,
            default=default if isinstance(default, bool) else None,
        )

    if jstype == "array":
        return IO.Array.Input(
            id=prop_id,
            tooltip=description,
            optional=optional,
            default=default if isinstance(default, list) else None,
        )

    if jstype == "object":
        return IO.Object.Input(
            id=prop_id,
            tooltip=description,
            optional=optional,
            default=default if isinstance(default, dict) else None,
        )

    return IO.Any.Input(
        id=prop_id,
        tooltip=description,
        optional=optional,
        default=default,
    )


def json_schema_to_inputs(
    schema: dict[str, Any] | None,
    *,
    drop: set[str] | None = None,
) -> list[InputBase]:
    """Convert a JSON Schema ``object`` into a list of typed IO inputs.

    ``drop`` optionally removes top-level properties (e.g. keys already
    modelled as separate node inputs). Unknown or non-object schemas
    return an empty list.
    """
    if not isinstance(schema, dict):
        return []
    if schema.get("type") not in (None, "object"):
        return []
    props = schema.get("properties") or {}
    if not isinstance(props, dict):
        return []
    required = set(schema.get("required") or [])
    drop = drop or set()

    inputs: list[InputBase] = []
    for prop_id, prop_schema in props.items():
        if prop_id in drop:
            continue
        if not isinstance(prop_schema, dict):
            prop_schema = {}
        inputs.append(
            _build_input(prop_id, prop_schema, required=prop_id in required)
        )
    return inputs
