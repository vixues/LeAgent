"""Shared data-processing primitives for the tool framework.

This private subpackage provides the building blocks every data tool
uses so that inputs and outputs are handled uniformly:

* :class:`ArtifactRef` — a typed pointer to tabular data that lives
  outside the LLM context window (local file, MinIO object, DataFrame
  cached by id). Accepted as an alternative to inline ``data`` on every
  data tool.
* :class:`TabularSchema` — column names, dtypes, row count, null counts,
  inferred from a pandas DataFrame or a list of records.
* :func:`iter_chunks` / :func:`iter_chunks_df` — chunked iteration so
  huge datasets don't need to be materialised end-to-end.
* :class:`ProgressReporter` — throttled wrapper over a
  :data:`ToolProgressCallback` that emits structured events during
  chunked work.
* :func:`load_records` / :func:`load_dataframe` — resolve either inline
  records or an :class:`ArtifactRef` into pandas-friendly shapes.
* :func:`emit_records` / :func:`emit_dataframe` — build a uniform
  output envelope that spills to disk/MinIO when the result exceeds
  configured limits and returns a preview + artifact reference instead
  of flooding the caller.
"""

from leagent.tools._data.artifacts import (
    ArtifactRef,
    is_artifact_ref,
    parse_artifact_ref,
)
from leagent.tools._data.progress import ProgressReporter
from leagent.tools._data.records import (
    OutputEnvelope,
    emit_dataframe,
    emit_records,
    load_dataframe,
    load_records,
)
from leagent.tools._data.schema import TabularSchema, infer_schema
from leagent.tools._data.streams import iter_chunks, iter_chunks_df
from leagent.tools._data.tool_helpers import (
    INPUT_SCHEMA_FRAGMENT,
    build_result,
    extend_input_schema,
    resolve_input,
)

__all__ = [
    "ArtifactRef",
    "is_artifact_ref",
    "parse_artifact_ref",
    "TabularSchema",
    "infer_schema",
    "iter_chunks",
    "iter_chunks_df",
    "ProgressReporter",
    "OutputEnvelope",
    "load_records",
    "load_dataframe",
    "emit_records",
    "emit_dataframe",
    "INPUT_SCHEMA_FRAGMENT",
    "extend_input_schema",
    "resolve_input",
    "build_result",
]
