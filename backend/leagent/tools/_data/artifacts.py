"""Artifact references for tabular data.

An :class:`ArtifactRef` is a typed pointer to data that lives outside
the LLM context window. Data tools accept one interchangeably with an
inline ``data`` list, and emit one when the output would otherwise
exceed configured size thresholds.

Supported URI schemes (resolved in :mod:`leagent.tools._data.records`):

* ``file://<abs_path>`` / bare absolute path — local disk (json, jsonl,
  csv, parquet inferred from extension)
* ``minio://<bucket>/<key>`` — object in the configured MinIO bucket,
  read via the async :class:`FileStoreService` when a running event loop
  is reachable
* ``memory://<id>`` — registered in-process artifact (e.g. an upstream
  DataFrame kept for the lifetime of a workflow run)

The dataclass itself carries no I/O — it is a plain descriptor. Reading
and writing are done by the helpers in :mod:`records` so that the tool
bodies stay focused on transformation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["ArtifactRef", "is_artifact_ref", "parse_artifact_ref"]


ARTIFACT_KINDS = {"records", "dataframe", "parquet", "csv", "json", "jsonl", "binary"}


@dataclass
class ArtifactRef:
    """Pointer to tabular data stored outside the message payload."""

    uri: str
    kind: str = "records"
    row_count: int | None = None
    column_count: int | None = None
    size_bytes: int | None = None
    schema: dict[str, Any] | None = None
    preview: list[dict[str, Any]] | None = None
    content_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in ARTIFACT_KINDS:
            self.metadata.setdefault("original_kind", self.kind)
            self.kind = "records"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict representation."""
        out: dict[str, Any] = {"uri": self.uri, "kind": self.kind}
        if self.row_count is not None:
            out["row_count"] = self.row_count
        if self.column_count is not None:
            out["column_count"] = self.column_count
        if self.size_bytes is not None:
            out["size_bytes"] = self.size_bytes
        if self.schema is not None:
            out["schema"] = self.schema
        if self.preview is not None:
            out["preview"] = self.preview
        if self.content_type is not None:
            out["content_type"] = self.content_type
        if self.metadata:
            out["metadata"] = self.metadata
        return out

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ArtifactRef:
        """Re-hydrate from a JSON-safe dict."""
        return cls(
            uri=str(payload["uri"]),
            kind=str(payload.get("kind", "records")),
            row_count=payload.get("row_count"),
            column_count=payload.get("column_count"),
            size_bytes=payload.get("size_bytes"),
            schema=payload.get("schema"),
            preview=payload.get("preview"),
            content_type=payload.get("content_type"),
            metadata=dict(payload.get("metadata") or {}),
        )


def is_artifact_ref(value: Any) -> bool:
    """Return ``True`` if ``value`` looks like an :class:`ArtifactRef`."""
    if isinstance(value, ArtifactRef):
        return True
    if isinstance(value, dict) and "uri" in value:
        return True
    if isinstance(value, str):
        return (
            "://" in value
            or value.startswith("/")
            or value.endswith((".json", ".jsonl", ".csv", ".parquet"))
        )
    return False


def parse_artifact_ref(value: Any) -> ArtifactRef | None:
    """Coerce a loose input into an :class:`ArtifactRef`, else ``None``."""
    if isinstance(value, ArtifactRef):
        return value
    if isinstance(value, dict):
        if "uri" in value:
            return ArtifactRef.from_dict(value)
        if "artifact" in value and isinstance(value["artifact"], dict):
            return ArtifactRef.from_dict(value["artifact"])
    if isinstance(value, str):
        if "://" in value:
            kind = _kind_from_uri(value)
            return ArtifactRef(uri=value, kind=kind)
        if value.startswith("/") or value.endswith((".json", ".jsonl", ".csv", ".parquet")):
            return ArtifactRef(uri=f"file://{value}", kind=_kind_from_uri(value))
    return None


def _kind_from_uri(uri: str) -> str:
    lower = uri.lower()
    if lower.endswith(".parquet"):
        return "parquet"
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".jsonl"):
        return "jsonl"
    if lower.endswith(".json"):
        return "json"
    return "records"
