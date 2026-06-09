# Tool System, Data Processing & Code Execution

This document is the single reference for the tool layer after the
integration upgrade. It covers:

1. Tool-registry bootstrap.
2. Data-processing primitives.
3. Workflow integration (per-tool nodes, `ScriptNode`, `ScriptAgentNode`).
4. The two-tier code-execution stack.
5. Extending the system.

---

## 1. Bootstrap

Every entrypoint (HTTP server, CLI, workflow worker) populates the tool
registry and the workflow node registry through a single helper:

```python
from leagent.bootstrap import (
    bootstrap_tools,          # async: tools + nodes in one call
    register_default_tools,   # sync: tools only
    register_script_agent_tool, # expose the Script (compute) agent as a sub-tool
    register_workflow_tool_nodes, # async: builtins + factory only
)
```

Typical server startup:

```python
summary = await bootstrap_tools()
# summary = {"tools": 60, "nodes": [...], "node_summary": {...}}
```

After the first `AgentController` is built, expose the code-execution
agent as a sub-tool:

```python
register_script_agent_tool(registry, controller)
```

### Why one bootstrap?

Before the upgrade, `main.py`, `cli/bootstrap.py`, and the workflow
worker each maintained their own copy of "discover tools + register
curated util tools". They drifted — the CLI was missing several tools
the server had. The new module is the only place to add or remove an
always-on tool.

---

## 2. Data Processing Primitives

Heavy data tools (SQL, vector search, aggregation, cleaning,
transformation, merging, validation) share a set of primitives in
`leagent/tools/_data/`:

- `ArtifactRef` — opaque handle to a record stream stored in MinIO (or
  on disk). Tools accept either an inline array *or* an `ArtifactRef`
  via `oneOf`; the helper `load_records(...)` normalises the inputs.
- `TabularSchema` — typed column metadata emitted alongside results.
- `emit_records(...)` — writes rows to the response envelope with
  automatic spill-to-disk past configurable thresholds
  (`spill_rows`, `spill_bytes`, `force_spill`).
- `INPUT_SCHEMA_FRAGMENT` — pre-built JSON-schema fragment so every
  data tool advertises the same artifact/spill knobs.

All seven refactored data tools use these — a consumer can pass either
an artifact or an inline batch and receive the same envelope shape.

---

## 3. Workflow Integration

### 3.1 Per-tool nodes (`Tool.<name>`)

`workflow/nodes/tool_factory.py` + `workflow/io/schema_bridge.py`
dynamically generate a `WorkflowNode` subclass for every registered
tool:

- `schema_bridge.json_schema_to_inputs` converts a tool's JSON Schema
  into typed `IO.*` inputs (combo/string/int/number/boolean/array/
  object/any). Unknown shapes fall back to `Any` so an exotic tool
  schema can never brick the palette.
- `tool_factory.build_node_class(tool)` wraps that schema in a new
  class with `NODE_ID = "Tool.<tool.name>"` and an `execute()` that
  delegates to `ToolExecutor`.
- `tool_factory.register_tool_nodes(node_registry, tool_registry)`
  iterates over the tool registry and registers every generated class.

Bootstrap calls this automatically. A tool written today is a node in
tomorrow's palette — no YAML, no frontend work.

### 3.2 `ScriptNode` — in-process scripts

`workflow/nodes/builtin/script.py` embeds RestrictedPython into a
dedicated workflow node so authors can write small Python snippets
inline:

```yaml
- id: "tally"
  type: "script"
  inputs:
    source: |
      result = sum(rows)
    inputs:
      rows: "${prev.values}"
    timeout_sec: 3.0
```

Runtime contract:

- Sandbox: `leagent/tools/_sandbox/inproc.py`. Curated stdlib
  allow-list (math, statistics, json, re, datetime, decimal, random,
  itertools, functools, collections, …). **No** `open`, `socket`,
  `subprocess`, `os`, `eval`, or `__import__` bypass.
- Outputs: `result` (top-level variable), `stdout` (captured prints),
  `stderr` (currently empty — reserved for a future kill-channel).
- Timeout: runs on a daemon `threading.Thread`; `asyncio.wait_for`
  raises `ScriptTimeoutError` and the process remains exit-clean.

### 3.3 `ScriptAgentNode` — delegate to the Script (compute) Agent

```yaml
- id: "analyse"
  type: "script_agent"
  inputs:
    prompt: "Load ${inputs.path} and report the top 5 rows by amount."
    max_iterations: 8
    allowed_tools: ["code_execution", "data_clean", "csv_processor"]
```

The node reads the parent `AgentController` from the executor context,
calls `build_script_execution_agent(parent=...)`, and runs the prompt to
completion. Use this when the turn is iterative — load data, inspect,
refine — rather than a one-shot snippet.

---

## 4. Two-Tier Code Execution

### Tier 1 — In-process (`ScriptNode`)

- **Module**: `leagent.tools._sandbox.inproc.execute_script`.
- **Purpose**: evaluate tiny pure-Python snippets inside a workflow
  without forking a subprocess.
- **Why RestrictedPython**: AST-level rewrite (not a linter), no network
  primitives available, cheap to start (< 1 ms per call).
- **Use when**: stitching fields, arithmetic, dict/list reshaping,
  simple templating.

### Tier 2 — Subprocess (`code_execution` tool, `CodeExecutionAgent`)

- **Modules**: `leagent.services.code_execution.{workspace,subprocess_sandbox,runner}`.
- **Isolation**:
  - Separate POSIX process (`start_new_session=True`).
  - `resource.setrlimit` on CPU, address space, file size, open files,
    and process count.
  - `signal.SIGALRM` inside the child as the hard stop; `asyncio.wait_for`
    in the parent as the last-resort kill.
  - Dedicated workspace per `(user_id, session_id)` tuple; filesystem
    writes are confined to that directory.
  - Env is stripped to a minimal allow-list (`PATH`, `HOME`, `LANG`, …).
- **Protocol**: parent writes a JSON payload on the child's stdin; the
  child responds with a JSON envelope on stdout
  (`status` / `stdout` / `stderr` / `result` / `produced_files` /
  `duration_ms`).
- **Use when**: scientific computing, CSV / parquet wrangling with
  pandas, multi-file generation, or anything where RestrictedPython's
  allow-list would bite.

---

## 5. Filesystem Path Sandbox

All tools that accept filesystem paths are subject to a central sandbox
enforced inside `BaseTool.run()` **before** execution begins. The sandbox
guarantees that the agent can never read or write files outside explicitly
allowed directories.

### How it works

1. Each tool class declares which of its JSON-schema parameters are
   filesystem paths via two class attributes:

   ```python
   class MyTool(SyncTool):
       path_params = ("file_path",)          # read-only paths (strict resolve)
       output_path_params = ("output_path",)  # write paths (allow_create=True)
   ```

2. `BaseTool.run()` iterates over those tuples and calls
   `PathSandbox.resolve_safe()` for each non-empty value. If the
   resolved absolute path does not fall under any allowed root **or**
   any per-request attachment, execution is short-circuited and a
   `ToolResult.fail(...)` is returned to the LLM.

3. Tools with **nested** path parameters (arrays of objects, artifact
   URIs, etc.) override `_enforce_path_sandbox(params, context)` to
   walk their own structure — see `ArchiveManagerTool`,
   `DataMergeTool`, `VectorSearchTool`, `TemplateFillerTool`, and
   `EmailSendTool` for examples.

### Allowed roots (matrix)

| Layer | Source | What it allows |
|---|---|---|
| Global | `LEAGENT_TOOL_FILE_ROOTS` (comma-separated abs paths) | Process-wide read/write roots for every tool call. When unset, defaults to `FilesSettings.upload_dir` (see `leagent/config/settings.py`). |
| Global | `FilesSettings.resolved_knowledge_storage_dir()` | Knowledge / indexed document blobs (`…/knowledge/documents`). Always merged into the sandbox allow-list so `@knowledge:` paths resolve even when `LEAGENT_TOOL_FILE_ROOTS` is narrowed. |
| Global (single-machine) | Desktop / local profile | When `LEAGENT_TOOL_FILE_ROOTS` is **not** set, `LEAGENT_HOME` and `WORKING_DIR` are also appended (`leagent/file/sandbox.py`). **Production tip:** set `LEAGENT_TOOL_FILE_ROOTS` explicitly instead of relying on this wide default. |
| Per request (files) | `ToolContext.extra["attachments"]` | Absolute storage paths for chat uploads, merged knowledge files, etc. |
| Per request (lookup) | `ToolContext.extra["attachment_lookup"]` | `by_id` / `by_name` maps for `@file:` / `@knowledge:` and UUID-prefixed filenames (`session_attachment_context.py`). |
| Per request (dirs) | `ToolContext.extra["project_roots"]` | Code-project / Folder `project_path` directories for `project_*` and `coding_agent` (`AgentController._run_via_query_engine`). |
| Per request (dirs) | `ToolContext.extra["authorized_roots"]` | Directories the user explicitly granted for this chat session (`POST /api/v1/chat/sessions/{id}/authorized-paths`). Same directory rules as `project_roots`. |

Prompt policy `policies/file_access.md` (server mode) tells the model to stay within attachments; `policies/file_access_local.md` matches the relaxed sandbox for desktop/local.

**Knowledge vs chat uploads:** chat session files live under `upload_dir/<session_id>/`; knowledge documents live under `resolved_knowledge_storage_dir()/documents/`. Migrating from the old layout (`upload_dir/documents/`) is a one-time copy — see `CHANGELOG.md`.

### Denial logging

Every blocked path emits a structured warning:

```
path_sandbox_denied  tool=file_manager  request_id=abc123
  attempted_path=/home/user/project/main.py
  allowed_roots=['/tmp/leagent/files']
```

No file contents are ever included in the log.

### Testing

Set `LEAGENT_TOOL_FILE_ROOTS` to include your test `tmp_path`:

```python
os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
reset_roots()  # from leagent.file.sandbox
```

The shared `conftest.py` fixture `_widen_sandbox_for_tests` does this
automatically (session-scoped, adds `/tmp`).

---

## 6. Extending the System

### Adding a tool

1. Create the class under `leagent/tools/{doc,data,web,gen,integration,util}/your_tool.py`.
2. Implement `parameters` (JSON Schema) and `execute` (async or via `SyncTool`).
3. If the constructor takes no args, auto-discovery picks it up.
4. If it needs runtime deps, add `(module_path, class_name)` to
   `_CURATED_UTIL_TOOL_PATHS` in `leagent/bootstrap/tools.py`.

No further work is required — the workflow factory generates
`Tool.your_tool` automatically.

### Adding a workflow node

Drop it into `leagent/workflow/nodes/builtin/your_node.py`, register
it in `workflow/nodes/builtin/__init__.py::BUILTIN_NODES`, and if you
want YAML authoring, map the YAML `type` string in
`workflow/io/authoring._TYPE_TO_CLASS`.

### Writing tests

`tests/test_tool_bootstrap_and_factory.py` and
`tests/test_code_execution.py` demonstrate the recommended patterns:

- Use `pytest.mark.asyncio` for async flows.
- For sandbox tests, pass explicit `timeout_sec` so a regression can't
  stall CI.
- Use `tempfile.TemporaryDirectory()` as the workspace root so the
  filesystem is isolated per test.
