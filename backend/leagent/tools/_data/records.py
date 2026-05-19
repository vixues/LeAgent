"""Record-level I/O helpers with artifact support and automatic spill.

This is the glue layer between tool bodies and the storage/artifact
primitives. Data tools call exactly two functions:

* :func:`load_records` at the start: accepts an inline ``list[dict]``
  or an :class:`ArtifactRef` (including a bare filesystem path or a
  ``minio://`` URI) and returns a ``list[dict]`` ready for pandas.
* :func:`emit_records` at the end: given the result records and the
  calling :class:`ToolContext`, returns a JSON-safe envelope that
  either embeds the records (small results) or writes them to a temp
  file / MinIO object and returns an :class:`ArtifactRef` plus a short
  preview (large results).

The spill thresholds default to "fits comfortably in a tool message"
(≤ 50 000 rows AND ≤ 5 MiB JSON). Tools can override per-call.

All helpers are synchronous so they work inside ``SyncTool.execute_sync``
worker threads; MinIO uploads are bridged via :func:`asyncio.run` when
no running loop is detected, or scheduled onto the active loop with
:func:`asyncio.run_coroutine_threadsafe` when the tool is executing in
a worker thread attached to a running event loop.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import structlog

from leagent.tools._data.artifacts import ArtifactRef, parse_artifact_ref
from leagent.tools._data.schema import TabularSchema, infer_schema

if TYPE_CHECKING:  # pragma: no cover
    from leagent.tools.base import ToolContext

logger = structlog.get_logger(__name__)


__all__ = [
    "OutputEnvelope",
    "load_records",
    "load_dataframe",
    "emit_records",
    "emit_dataframe",
]


DEFAULT_SPILL_ROWS = 50_000
DEFAULT_SPILL_BYTES = 5 * 1024 * 1024
DEFAULT_PREVIEW_ROWS = 20


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


@dataclass
class OutputEnvelope:
    """Uniform tool-output structure built by :func:`emit_records`.

    Either ``data`` is populated (small results) or ``artifact`` is
    populated (spilled results) — never both. ``schema`` and
    ``row_count`` are always present when input was tabular.
    """

    data: list[dict[str, Any]] | None
    artifact: ArtifactRef | None
    schema: TabularSchema
    row_count: int
    preview: list[dict[str, Any]] | None = None
    spilled: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "row_count": self.row_count,
            "schema": self.schema.to_dict(),
            "spilled": self.spilled,
        }
        if self.artifact is not None:
            out["artifact"] = self.artifact.to_dict()
            if self.preview is not None:
                out["preview"] = self.preview
        else:
            out["data"] = self.data or []
        return out


# ---------------------------------------------------------------------------
# Input side
# ---------------------------------------------------------------------------


def load_records(
    value: Any,
    context: "ToolContext | None" = None,
    *,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    """Resolve ``value`` into a list of row dicts.

    Accepted shapes:

    * ``list[dict]`` — returned directly (optionally truncated to
      ``max_rows``)
    * ``ArtifactRef`` or ``{"uri": ..., ...}`` — read from the
      referenced storage
    * Bare path string, ``file://`` URI, or ``minio://bucket/key``
    * ``None`` — empty list
    """
    if value is None:
        return []

    if isinstance(value, list):
        if max_rows is not None and len(value) > max_rows:
            return list(value[:max_rows])
        return [dict(row) if isinstance(row, dict) else row for row in value]

    ref = parse_artifact_ref(value)
    if ref is None:
        raise ValueError(
            f"Unsupported records input of type {type(value).__name__}: "
            "expected list of dicts or an artifact reference"
        )

    records = _read_artifact(ref, context)
    if max_rows is not None and len(records) > max_rows:
        records = records[:max_rows]
    return records


def load_dataframe(
    value: Any,
    context: "ToolContext | None" = None,
    *,
    max_rows: int | None = None,
) -> Any:
    """Resolve ``value`` into a pandas DataFrame."""
    import pandas as pd

    if hasattr(value, "columns") and hasattr(value, "iloc"):
        return value if max_rows is None else value.head(max_rows)

    records = load_records(value, context, max_rows=max_rows)
    return pd.DataFrame(records)


def _read_artifact(ref: ArtifactRef, context: "ToolContext | None") -> list[dict[str, Any]]:
    scheme, location = _split_uri(ref.uri)
    if scheme in ("", "file"):
        return _read_local(Path(location), ref.kind)
    if scheme == "minio":
        return _read_minio(location, ref.kind, context)
    if scheme == "memory":
        return _read_memory(location, context)
    raise ValueError(f"Unsupported artifact scheme: {scheme!r}")


def _split_uri(uri: str) -> tuple[str, str]:
    if "://" not in uri:
        return "", uri
    parsed = urlparse(uri)
    location = parsed.netloc + parsed.path if parsed.netloc else parsed.path
    return parsed.scheme, location.lstrip("/") if parsed.scheme == "minio" else location


def _read_local(path: Path, kind: str) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Artifact path does not exist: {path}")

    suffix = path.suffix.lower()
    if kind == "parquet" or suffix == ".parquet":
        import pandas as pd
        return pd.read_parquet(path).to_dict(orient="records")
    if kind == "csv" or suffix == ".csv":
        from leagent.tools.path_safe import open_read_text_nofollow

        with open_read_text_nofollow(path, newline="") as fh:
            return list(csv.DictReader(fh))
    if kind == "jsonl" or suffix == ".jsonl":
        from leagent.tools.path_safe import open_read_text_nofollow

        out: list[dict[str, Any]] = []
        with open_read_text_nofollow(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
    # default: json
    from leagent.tools.path_safe import open_read_text_nofollow

    with open_read_text_nofollow(path) as fh:
        text = fh.read()
    data = json.loads(text)
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return [r for r in data["data"] if isinstance(r, dict)]
    raise ValueError(f"JSON artifact does not contain a list of records: {path}")


def _read_minio(
    location: str,
    kind: str,
    context: "ToolContext | None",
) -> list[dict[str, Any]]:
    file_store = getattr(context, "file_store", None) if context else None
    if file_store is None:
        raise RuntimeError(
            "MinIO artifact requested but ToolContext has no file_store. "
            "Wire a ServiceManager through build_tool_context()."
        )
    bucket, _, key = location.partition("/")
    if not key:
        raise ValueError(f"MinIO URI missing object key: minio://{location}")

    data_bytes = _bridge_sync(_download_minio(file_store, bucket, key))
    return _parse_bytes_as_records(data_bytes, kind=kind, hint=key)


def _read_memory(
    handle: str, context: "ToolContext | None",
) -> list[dict[str, Any]]:
    if context is None:
        raise RuntimeError("memory:// artifact requires a ToolContext")
    registry = (context.extra or {}).get("_memory_artifacts") or {}
    if handle not in registry:
        raise KeyError(f"memory artifact not found: {handle}")
    value = registry[handle]
    if isinstance(value, list):
        return list(value)
    if hasattr(value, "to_dict"):
        return value.to_dict(orient="records")  # type: ignore[no-any-return]
    raise TypeError(f"unsupported memory artifact type: {type(value).__name__}")


def _parse_bytes_as_records(
    data: bytes, *, kind: str, hint: str,
) -> list[dict[str, Any]]:
    lower_hint = hint.lower()
    if kind == "parquet" or lower_hint.endswith(".parquet"):
        import pandas as pd
        return pd.read_parquet(io.BytesIO(data)).to_dict(orient="records")
    text = data.decode("utf-8")
    if kind == "csv" or lower_hint.endswith(".csv"):
        return list(csv.DictReader(io.StringIO(text)))
    if kind == "jsonl" or lower_hint.endswith(".jsonl"):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    parsed = json.loads(text)
    if isinstance(parsed, list):
        return [r for r in parsed if isinstance(r, dict)]
    if isinstance(parsed, dict) and "data" in parsed:
        return [r for r in parsed["data"] if isinstance(r, dict)]
    raise ValueError(f"MinIO artifact is not tabular: {hint}")


# ---------------------------------------------------------------------------
# Output side
# ---------------------------------------------------------------------------


def emit_records(
    records: list[dict[str, Any]],
    context: "ToolContext | None" = None,
    *,
    op_name: str = "data",
    preview_rows: int = DEFAULT_PREVIEW_ROWS,
    spill_rows: int = DEFAULT_SPILL_ROWS,
    spill_bytes: int = DEFAULT_SPILL_BYTES,
    force_spill: bool = False,
) -> OutputEnvelope:
    """Wrap ``records`` in an :class:`OutputEnvelope`, spilling when oversize.

    When the record list is small it is embedded directly. When it
    exceeds either threshold (or ``force_spill=True``) the data is
    written to disk (or MinIO when a file store is reachable) and the
    envelope contains only a short preview plus an :class:`ArtifactRef`.
    """
    schema = infer_schema(records)
    row_count = len(records)
    encoded_size = _estimate_json_size(records) if records else 0
    should_spill = (
        force_spill
        or row_count > spill_rows
        or encoded_size > spill_bytes
    )

    if not should_spill:
        return OutputEnvelope(
            data=records,
            artifact=None,
            schema=schema,
            row_count=row_count,
            preview=None,
            spilled=False,
        )

    ref = _spill_records(
        records,
        context,
        op_name=op_name,
        size_bytes=encoded_size,
        schema=schema,
    )
    preview = records[:preview_rows]
    return OutputEnvelope(
        data=None,
        artifact=ref,
        schema=schema,
        row_count=row_count,
        preview=preview,
        spilled=True,
    )


def emit_dataframe(
    df: Any,
    context: "ToolContext | None" = None,
    *,
    op_name: str = "data",
    preview_rows: int = DEFAULT_PREVIEW_ROWS,
    spill_rows: int = DEFAULT_SPILL_ROWS,
    spill_bytes: int = DEFAULT_SPILL_BYTES,
    force_spill: bool = False,
) -> OutputEnvelope:
    """DataFrame-friendly variant of :func:`emit_records`."""
    records = df.to_dict(orient="records")
    return emit_records(
        records,
        context,
        op_name=op_name,
        preview_rows=preview_rows,
        spill_rows=spill_rows,
        spill_bytes=spill_bytes,
        force_spill=force_spill,
    )


# ---------------------------------------------------------------------------
# Spill implementation
# ---------------------------------------------------------------------------


def _spill_records(
    records: list[dict[str, Any]],
    context: "ToolContext | None",
    *,
    op_name: str,
    size_bytes: int,
    schema: TabularSchema,
) -> ArtifactRef:
    artifact_id = uuid.uuid4().hex[:12]
    basename = f"{op_name}_{artifact_id}.jsonl"
    payload = _encode_jsonl(records)

    file_store = getattr(context, "file_store", None) if context else None
    session_id = getattr(context, "session_id", None) if context else None

    if file_store is not None:
        try:
            key = _upload_minio(file_store, session_id, basename, payload)
            return ArtifactRef(
                uri=f"minio://{key}",
                kind="jsonl",
                row_count=len(records),
                column_count=schema.column_count,
                size_bytes=len(payload),
                schema=schema.to_dict(),
                content_type="application/x-ndjson",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "records_spill_minio_failed_fallback_local",
                error=str(exc),
                op=op_name,
            )

    temp_dir = getattr(context, "temp_dir", None) if context else None
    base = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)
    path = base / basename
    path.write_bytes(payload)
    return ArtifactRef(
        uri=f"file://{path}",
        kind="jsonl",
        row_count=len(records),
        column_count=schema.column_count,
        size_bytes=len(payload),
        schema=schema.to_dict(),
        content_type="application/x-ndjson",
    )


def _encode_jsonl(records: list[dict[str, Any]]) -> bytes:
    buf = io.BytesIO()
    for record in records:
        buf.write(json.dumps(record, ensure_ascii=False, default=_json_default).encode("utf-8"))
        buf.write(b"\n")
    return buf.getvalue()


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            pass
    return str(value)


def _estimate_json_size(records: list[dict[str, Any]]) -> int:
    if not records:
        return 0
    sample_size = min(100, len(records))
    sample_bytes = sum(
        len(json.dumps(r, ensure_ascii=False, default=_json_default))
        for r in records[:sample_size]
    )
    if sample_size == 0:
        return 0
    return int(sample_bytes / sample_size * len(records))


def _upload_minio(file_store: Any, session_id: str | None, name: str, payload: bytes) -> str:
    """Upload via :class:`FileStoreService`. Returns ``bucket/key``."""
    prefix = session_id or "anonymous"
    object_key = f"artifacts/{prefix}/{name}"
    bucket = _bridge_sync(_upload_helper(file_store, object_key, payload))
    return f"{bucket}/{object_key}"


async def _upload_helper(file_store: Any, key: str, payload: bytes) -> str:
    """Async helper that uploads and returns the bucket name."""
    bucket = getattr(file_store, "default_bucket", None) or "leagent"
    data = io.BytesIO(payload)
    if hasattr(file_store, "upload"):
        await file_store.upload(
            bucket=bucket,
            object_name=key,
            data=data,
            length=len(payload),
            content_type="application/x-ndjson",
        )
    else:  # pragma: no cover - defensive fallback
        client = getattr(file_store, "_client", None)
        if client is None:
            raise RuntimeError("file_store has neither upload() nor _client")
        await asyncio.to_thread(
            client.put_object,
            bucket, key, data, len(payload),
            content_type="application/x-ndjson",
        )
    return bucket


async def _download_minio(file_store: Any, bucket: str, key: str) -> bytes:
    if hasattr(file_store, "download"):
        result = await file_store.download(bucket=bucket, object_name=key)
        if isinstance(result, (bytes, bytearray)):
            return bytes(result)
        if hasattr(result, "read"):
            return result.read()
        return bytes(result)
    client = getattr(file_store, "_client", None)
    if client is None:
        raise RuntimeError("file_store has neither download() nor _client")
    response = await asyncio.to_thread(client.get_object, bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


# ---------------------------------------------------------------------------
# Async bridge
# ---------------------------------------------------------------------------


def _bridge_sync(coro: Any) -> Any:
    """Run an async coroutine from a synchronous context.

    - If there's no running loop in the current thread: use ``asyncio.run``.
    - If we're in a worker thread attached to a running loop elsewhere:
      schedule with ``run_coroutine_threadsafe``.
    - If we're on the loop thread itself: this is a programming error;
      raise loudly.
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running is None:
        return asyncio.run(coro)

    # We're inside a loop — check whether we're on the loop thread.
    try:
        import threading
        loop_thread = getattr(running, "_thread_id", None)
        if loop_thread is not None and loop_thread == threading.get_ident():
            raise RuntimeError(
                "Cannot call synchronous artifact helper from the event-loop thread; "
                "use the async variant or offload via asyncio.to_thread."
            )
    except Exception:  # noqa: BLE001
        pass

    fut = asyncio.run_coroutine_threadsafe(coro, running)
    return fut.result(timeout=float(os.environ.get("LEAGENT_ARTIFACT_TIMEOUT", "60")))
