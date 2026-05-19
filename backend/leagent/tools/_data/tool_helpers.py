"""Reusable helpers so data tools stay concise.

These bind together :mod:`records` and :mod:`schema` into the two
one-liners every data tool needs at its entry and exit points:

* :func:`resolve_input` — decode the ``data`` / ``artifact`` / file-path
  parameter into a list of row dicts
* :func:`build_result` — convert the final records into the tool's
  returned dict, spilling automatically when appropriate

The JSON-schema fragment :data:`INPUT_SCHEMA_FRAGMENT` gives every data
tool the same "inline or artifact" input contract. Tools extend their
``parameters`` with it using :func:`extend_input_schema`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from leagent.tools._data.records import (
    DEFAULT_PREVIEW_ROWS,
    DEFAULT_SPILL_BYTES,
    DEFAULT_SPILL_ROWS,
    emit_records,
    load_records,
)

if TYPE_CHECKING:  # pragma: no cover
    from leagent.tools.base import ToolContext

__all__ = [
    "INPUT_SCHEMA_FRAGMENT",
    "extend_input_schema",
    "resolve_input",
    "build_result",
]


INPUT_SCHEMA_FRAGMENT: dict[str, Any] = {
    "data": {
        "type": "array",
        "description": (
            "Input rows as a list of objects. Provide either this, "
            "'artifact', or 'source_path'."
        ),
        "items": {"type": "object"},
    },
    "artifact": {
        "type": "object",
        "description": (
            "Artifact reference to tabular data stored outside the message "
            "payload (e.g. minio://bucket/key, file:///abs/path). Use instead "
            "of inlining large datasets."
        ),
        "properties": {
            "uri": {"type": "string"},
            "kind": {
                "type": "string",
                "enum": ["records", "jsonl", "json", "csv", "parquet"],
            },
        },
        "required": ["uri"],
        "additionalProperties": True,
    },
    "source_path": {
        "type": "string",
        "description": (
            "Path (or file:// URI) to a local JSON/JSONL/CSV/Parquet file. "
            "Convenience alias for 'artifact'."
        ),
    },
    "max_rows": {
        "type": "integer",
        "description": "Truncate the loaded input to this many rows.",
        "minimum": 1,
    },
    "spill_rows": {
        "type": "integer",
        "description": (
            "Spill the output to storage when it exceeds this many rows. "
            f"Default: {DEFAULT_SPILL_ROWS}."
        ),
        "minimum": 1,
    },
    "spill_bytes": {
        "type": "integer",
        "description": (
            "Spill the output when the encoded size exceeds this many "
            f"bytes. Default: {DEFAULT_SPILL_BYTES}."
        ),
        "minimum": 1024,
    },
    "force_spill": {
        "type": "boolean",
        "description": "Always spill the output to storage regardless of size.",
        "default": False,
    },
}


def extend_input_schema(
    properties: dict[str, Any],
    *,
    extra_required: list[str] | None = None,
) -> dict[str, Any]:
    """Merge :data:`INPUT_SCHEMA_FRAGMENT` into a tool's ``properties`` dict.

    ``properties`` is mutated and returned for convenience. ``data`` is
    made optional at the schema level because callers may supply
    ``artifact`` or ``source_path`` instead; tool bodies should assert
    that at least one is present.
    """
    for key, value in INPUT_SCHEMA_FRAGMENT.items():
        properties.setdefault(key, value)
    return properties


def resolve_input(
    params: dict[str, Any],
    context: "ToolContext | None" = None,
    *,
    data_key: str = "data",
    artifact_key: str = "artifact",
    path_key: str = "source_path",
    max_rows_key: str = "max_rows",
    required: bool = True,
) -> list[dict[str, Any]]:
    """Decode the usual trio of input params into a list of row dicts."""
    value = params.get(data_key)
    if value is None:
        value = params.get(artifact_key)
    if value is None:
        value = params.get(path_key)
    if value is None:
        if required:
            raise ValueError(
                f"No input provided: pass '{data_key}', '{artifact_key}', "
                f"or '{path_key}'."
            )
        return []
    max_rows = params.get(max_rows_key)
    return load_records(value, context, max_rows=max_rows)


def build_result(
    records: list[dict[str, Any]],
    context: "ToolContext | None" = None,
    *,
    op_name: str,
    extra: dict[str, Any] | None = None,
    output_format: str = "records",
    params: dict[str, Any] | None = None,
    preview_rows: int = DEFAULT_PREVIEW_ROWS,
    spill_rows: int = DEFAULT_SPILL_ROWS,
    spill_bytes: int = DEFAULT_SPILL_BYTES,
) -> dict[str, Any]:
    """Convert ``records`` into a full tool-output dict.

    When ``output_format == "dict"`` and the result is small, the data
    is transposed to a column-oriented dict. Large results always spill
    to JSONL for efficient roundtripping.
    """
    if params:
        spill_rows = int(params.get("spill_rows", spill_rows))
        spill_bytes = int(params.get("spill_bytes", spill_bytes))
        force_spill = bool(params.get("force_spill", False))
    else:
        force_spill = False

    envelope = emit_records(
        records,
        context,
        op_name=op_name,
        preview_rows=preview_rows,
        spill_rows=spill_rows,
        spill_bytes=spill_bytes,
        force_spill=force_spill,
    )

    payload = envelope.to_dict()
    if output_format == "dict" and payload.get("data") and isinstance(payload["data"], list):
        cols: dict[str, list[Any]] = {}
        for row in payload["data"]:
            if not isinstance(row, dict):
                continue
            for col, val in row.items():
                cols.setdefault(col, []).append(val)
        payload["data"] = cols

    if extra:
        for key, value in extra.items():
            payload.setdefault(key, value)

    return payload
