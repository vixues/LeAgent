# LeAgent Service-Layer & Data-Persistence Migration Spec

> Scope: backend topology (`backend/leagent/`), the managed-blob ingress
> (`FileService`), the structured-data layer (`DatabaseService`), and the
> architectural invariants enforced by `backend/tests/test_file/test_invariants.py`.
>
> Cross-references: [`docs/fastapi-api-layer-review.md`](./fastapi-api-layer-review.md)
> (API-layer findings) and the LUFS design spec
> (`.cursor/plans/lufs_design_spec_8adfe623.plan.md`).
>
> Status: actionable migration spec. Phases are independently shippable.

---

## 0. How this connects to the API-layer review

The FastAPI review (`fastapi-api-layer-review.md`) found that the HTTP layer
"reads like a fast-moving monolithic backend rather than a hardened public API,"
with three root causes that this spec addresses at the layer beneath the router:

| API-review finding | Service-layer root cause | Addressed in |
|---|---|---|
| §2.1 Oversized routers (`chat.py` ~3200, `files.py` ~825) | Business logic and persistence live in handlers because no thin service seam exists | §1 Topology, §2 Ingress |
| §4.3 Business logic in controllers | `Router → Service → Repository` only partially realized | §1, §5 Phases |
| §6.1 `BackgroundTasks` for heavy work in `files.py`/`documents.py` | File ingest + processing is inline in handlers, not behind `FileService` | §2, §3 Audit |
| §4.2 Weakly typed `get_db_service() -> Any` | DB layer is a "service" but not a typed infra boundary | §1 (db/ promotion), §4 |

The guiding principle: **`services/` is the application-service layer (thin,
orchestrating, lifecycle-managed), not a container for all backend logic.**
Capabilities sink into `file/`, `code/`, `project/`, and a promoted `db/`;
routers get thin.

---

## 1. Target Topology

### 1.1 Layer model

```
┌──────────────────────────────────────────────────────────────┐
│  api/            HTTP ingress: auth deps, DTOs, thin handlers  │
├──────────────────────────────────────────────────────────────┤
│  agent/          LLM loop, tool dispatch, streaming            │
├──────────────────────────────────────────────────────────────┤
│  services/       Application services — use-case orchestration │  ← THIN
│                  (ChatService, SessionManager, CanvasService,  │
│                   TaskManager, VariableService, ServiceManager)│
├──────────┬──────────┬──────────┬──────────┬───────────────────┤
│ workflow/│  cron/   │  memory/ │  llm/    │  rules/            │  ← domain subsystems
├──────────┴──────────┴──────────┴──────────┴───────────────────┤
│  file/   │  code/   │  project/ │  tools/                      │  ← capability layer
├──────────┴──────────┴───────────┴──────────────────────────────┤
│  db/   │  auth/   │  config/   │  leagent_core/                │  ← infrastructure
└──────────────────────────────────────────────────────────────┘
            dependencies flow downward only
```

### 1.2 Concrete moves

| Current location | Target | Rationale | Mechanism |
|---|---|---|---|
| `services/database/` | `leagent/db/` (service, models, sqlite_compat, repositories) | DB is infrastructure, not an application service; `DatabaseService` does not even subclass `Service` | Physical move + re-export shim |
| `services/coding_projects/` | `leagent/project/` | Already migrated; shim re-exports | Keep shim, delete after callers move |
| `services/code_execution/` | `leagent/code/` | Already migrated; shim re-exports | Keep shim, delete after callers move |
| `services/file_manager/`, `services/file_store/` | `leagent/file/` (`FileService`) | LUFS consolidation | Migrate callers, then delete |
| `services/gen_ui/` | `leagent/services/canvas/renderers/` or `leagent/rendering/` | Pure renderers, no lifecycle | Optional, P2 |
| `services/file_processing/` | `leagent/file/processing/` | Post-ingest pipeline belongs with `file/` | Optional, P2 |
| `services/diagnostics_parsers/` | `leagent/code/` or `tools/` | Parsing helpers, no lifecycle | Optional, P2 |

### 1.3 What stays in `services/`

Application services that (a) have a managed lifecycle via `ServiceManager`,
(b) orchestrate multiple lower layers, and (c) express a use case:
`ChatService`, `SessionManager`, `CanvasService`, `TaskManager`,
`VariableService`, `EventManager`, `WebhookEventManager`, `CacheService`,
`ServiceManager`.

### 1.4 Decision rule for new modules

```
Is it an HTTP route/DTO?              → api/
Is it the LLM loop / tool dispatch?   → agent/ or tools/
Does it persist a managed blob?       → file/  (via FileService.register)
Does it run code / a sandbox?         → code/
Does it edit a project source tree?   → project/
Is it SQL / table schema / migration? → db/
Does it orchestrate a use case across subsystems? → services/
Is it a self-contained subsystem?     → top-level domain package
Is it a stateless helper?             → attach to nearest domain package; do NOT make a Service
```

---

## 2. Ingress Boundaries

Each persistence domain has **exactly one ingress**. Everything else delegates.

| Domain | Single ingress | Backend(s) | Boundary rule |
|---|---|---|---|
| Managed blobs (Tier A) | `FileService.register()` (`backend/leagent/file/service.py`) | `StorageBackend` (Local now, S3/GCS later) | No `open(..., 'wb')` / `write_bytes` outside `StorageBackend` impls |
| Structured data | `DatabaseService.session()` (`backend/leagent/db/service.py` post-move) | SQLite (default) / PostgreSQL | API handlers do not hand-roll engines; use repositories |
| Project workspace (Tier B) | `project.fs.resolve_in_project()` + direct write | Local FS | Never creates a `File` DB row; never calls `FileService.register()` |
| Code sandbox (Tier B) | `code.workspace` write helpers | Local FS | Promotes artifacts to Tier A only via explicit `register()` |
| Vector memory | `memory/*Store.record()` | Milvus (optional) | DB row first, vector best-effort |
| Session state | `TieredSessionStore.save()` | LRU + DB JSON blob | Single SSOT decision (see §3.3) |

### 2.1 Tier A ↔ Tier B boundary (must never blur)

```mermaid
flowchart LR
  subgraph A [Tier A — managed blobs]
    reg["FileService.register()"]
    ref["FileRef + File row"]
  end
  subgraph B [Tier B — mutable workspaces]
    pw["project_write / project_edit"]
    cw["code workspace write"]
  end
  A -. "copy-only, explicit export" .-> B
  B -. "copy-only, explicit export" .-> A
  pw -.x|"NEVER creates File row"| ref
```

- A blob output (chart, export, screenshot) MUST register via `FileService`.
- A project edit MUST NOT create a `File` row.
- Cross-tier transfers are copy-only, never move/symlink.

---

## 3. Data-Persistence Recommendations

### 3.1 Storage-backend contract

The `StorageBackend` protocol (`backend/leagent/file/storage/backend.py`) is the
correct seam and must be preserved as the only filesystem-aware surface:

```19:38:backend/leagent/file/storage/backend.py
    async def put(
        self,
        data: bytes | BinaryIO,
        key: str,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        ...

    async def get(self, key: str) -> tuple[bytes, str]:
        ...

    async def delete(self, key: str) -> bool:
        ...

    async def exists(self, key: str) -> bool:
        ...

    async def presign(self, key: str, *, expires_in: int = 3600) -> str | None:
        ...
```

Contract requirements (graduating the LUFS plan §13 into rules):

1. **Opaque keys.** Storage keys are strings, never `Path`. `LocalStorageBackend`
   interprets them as relative paths; an S3 backend uses them as object keys.
2. **`put()` returns metadata** (`size`, `checksum`, `storage_path`/URL). Callers
   never assume where bytes landed.
3. **`presign()` returns `None` for local** (served via the `/api/v1/files/`
   proxy) and a real URL for object stores. Frontend handles both.
4. **No `Path` leakage past the backend boundary** (LUFS plan INV-10). No
   `path.stat()` / `path.is_file()` on blob access outside the backend.
5. **`backend_name` on `FileRef`** enables mixed-backend deployments during
   migration; existing refs stay valid if data is migrated.

### 3.2 Metadata lifecycle

`FileService.register()` already implements the canonical sequence
(`backend/leagent/file/service.py`): sanitize → size-check → `backend.put()` →
build `FileRef` → cache → `_persist_db_row()`. Harden it as the contract:

```
register(data, *, filename, content_type, user_id, session_id,
         scope, category, metadata) -> FileRef

post-conditions:
  1. bytes persisted under deterministic key  {scope_prefix}/{file_id}_{safe}
  2. File DB row created (status=PROCESSED or UPLOADED)
  3. FileRef cached in-memory + (optionally) cache service
  4. session/output scope → visible in list_session_attachments
  5. signed URLs derivable from the ref
  6. post-ingest processing enqueued (never blocks register)
```

Lifecycle states on the `File` row should separate **blob identity** (id, name,
storage_path, checksum, mime, size) from **post-processing state**
(extracted_text, page_count, has_ocr, embedding_id, is_indexed). Processing
updates the latter asynchronously; `register()` only writes identity.

`resolve()` must fall through **in-memory → cache → DB** (already present at
`backend/leagent/file/service.py` `_resolve_from_db`). The in-memory `_refs`
dict is an L1 cache only and must never be the source of truth.

### 3.3 Session / output scoping

Adopt the closed scope set from `FileScope`
(`backend/leagent/file/primitives.py`) as the only namespace authority:

| Scope | Disk layout | Semantics | Lifetime |
|---|---|---|---|
| `session` | `{upload_root}/{session_id}/` | Chat uploads | Session (+ retention) |
| `output` | `{upload_root}/{session_id}/` | Tool-generated artifacts | Same as session |
| `knowledge` | `{knowledge_root}/{user_id}/` | KB documents | Until user deletes |
| `asset` | `{upload_root}/assets/{user_id}/` | Pet/profile/long-lived | Until user deletes |
| `temp` | `{upload_root}/temp/` | Transient staging | Auto-purged |

Rules:

- Scope is set at registration time and is **immutable**.
- `FileService.get_scope_roots()` is the single source of truth for disk roots;
  `PathSandbox` consumes it rather than re-parsing env vars (LUFS INV-8).
- Storage key prefix derives from scope, so two files in different scopes never
  collide even with identical display names.

**Session-state SSOT.** `TieredSessionStore` currently keeps three views — LRU,
the `session_state_v1` JSON blob in `chat_sessions.session_metadata`, and the
`messages` table. Designate the JSON blob as the durable SSOT and the `messages`
table as a query/index projection written solely by `ChatService.add_message`.
This removes the user/assistant double-write hazard already documented in
`backend/leagent/services/session/store.py`.

---

## 4. Production-Path Audit — managed-blob writes

Goal: **every managed-blob creation goes through `FileService.register()`**, not
ad-hoc `open(..., 'wb')` / `write_bytes()` / `write_text()`.

The audit below classifies every blob-write call site found in
`backend/leagent/` into three buckets.

### 4.1 VIOLATIONS — production managed-blob paths to migrate

| Call site | What it writes | Action | Priority |
|---|---|---|---|
| `services/session/manager.py:273` (`open(storage_path, "wb")` chunk loop) | Chat attachment uploads | Delegate to `FileService.register(scope=SESSION)`; build `SessionAttachment` from returned `FileRef` | **P0** |
| `api/v1/files.py:211`, `:284` (`open(..., "wb")`) | File-upload endpoint persistence | Route through `FileService.register()` | **P0** |
| `api/v1/documents.py:214`, `:315` (`open(..., "wb")`) | Knowledge-doc upload + server-side copy | Route through `FileService.register(scope=KNOWLEDGE)` | **P0** |
| `tools/image/image_generate.py:159` (`out.write_bytes`) | Generated image | Register directly; stop double-writing then `register_external_file` | **P1** |
| `tools/web/screenshot.py:274` (`open(file_path, "wb")`) | Screenshot output | Register directly | **P1** |
| `tools/web/image_download.py:112` (`staging.write_bytes`) | Downloaded image | Register directly | **P1** |
| `tools/_data/records.py:394` (`path.write_bytes`) | Data records output | Register (scope OUTPUT) | **P1** |
| `tools/gen/report_generator.py:856`, `:959` | HTML/MD reports | Register (scope OUTPUT) | **P1** |
| `tools/gen/checklist_generator.py:598`, `:602`, `:737` | Checklist exports | Register (scope OUTPUT) | **P1** |
| `tools/gen/template_filler.py:282` | Filled template output | Register (scope OUTPUT) | **P1** |
| `tools/gen/pdf_generator.py:1186` (`open(..., "wb")`) | Generated PDF | Register (scope OUTPUT) | **P1** |
| `tools/doc/markdown_processor.py:46`, `html_processor.py:648`, `text_processor.py:590,993`, `config_file_tool.py:334,359,373`, `csv_processor.py:378,520` | Document tool outputs | Decide per call: sandbox-temp vs OUTPUT; register the user-facing results | **P2** |
| `tools/util/tool_argument_blob.py:209` (`path.write_bytes`) | Large tool-argument staging | Register (scope TEMP) or keep as sandbox-temp with explicit waiver | **P2** |

The double-write tools (`image_generate`, `screenshot`, `image_download`) are
called out in the LUFS plan §6 — they currently write a file *and* call
`register_external_file`. Collapse to a single `FileService.register()` call.

### 4.2 ALLOWED — Tier B mutable workspaces (must NOT register)

| Call site | Reason |
|---|---|
| `project/fs.py:466,741`, `project/tools/write.py:189` | Coding-project edits (Tier B) |
| `code/execution.py:987,1014`, `code/workspace.py:97,101` | Sandbox workspace writes (Tier B) |
| `skills/*` (`github_monorepo_catalog.py`, `manager.py`, `registry.py`, `url_install.py`, `package_skill.py`) | Skill package contents (Tier B) |

### 4.3 ALLOWED — infrastructure / config / CLI (not managed blobs)

| Call site | Reason |
|---|---|
| `llm/provider_config.py:234`, `config/config.py:94`, `config/migrate_v2.py:157,301` | Config files |
| `cli/*` (`init_cmd`, `config_cmd`, `env_cmd`, `cron_cmd`, `daemon_cmd`, `chats_cmd`, `chat_cmd`, `skills_cmd`, `rules_cmd`) | CLI-authored config/exports |
| `extensions/manager.py:72` | Installed-extensions manifest |
| `workflow/io/serializer.py:27,29` | Flow definition YAML/JSON (workflow defs, not blobs) |
| `cron/repository.py:366` | JSON job-repo atomic state file |
| `db/models/task.py:174` (append) | Task output log (append-mode log file) |
| `memory/agent_memory.py:143` (append) | Append-only memory log |
| `tools/web/login.py:281` | Tool-local session cookie cache |

These remain legal because they are not managed blobs. They must be encoded as
an **explicit allowlist** in the invariant test (§5.3) rather than relying on a
broad directory exclusion.

### 4.4 Anti-patterns the audit forbids going forward

(from LUFS plan §12) — direct `open()` for managed files; extending the
heuristic `extract_produced_path_candidates()` path-scraping; inline base64 in
tool results; new `_safe_filename`/`_sanitize_name` functions; project edits
creating `File` rows; `PathSandbox` deriving storage roots from env vars;
mutating a registered blob's storage key.

---

## 5. Rollout Phases

### Phase 0 — P0 blob ingress (highest ROI)

1. Migrate `SessionManager.attach_files` to `FileService.register(scope=SESSION)`.
2. Migrate `api/v1/files.py` upload paths to `FileService`.
3. Migrate `api/v1/documents.py` to `FileService.register(scope=KNOWLEDGE)`.
4. Preserve session semantics (INV-9): `list_session_attachments`, signed URLs,
   and SSE `attachments` events unchanged from the frontend's view.
5. Land §6 invariant test in **report-only** mode (collect violations, do not
   block).

Exit criteria: no `open(..., 'wb')` in `services/session/`, `api/v1/files.py`,
`api/v1/documents.py`; attachment E2E tests green.

### Phase 1 — P1 tool-output registration

1. Convert artifact-producing tools to return `FileRef` via
   `ToolResult.produced_files` (the field already exists at
   `backend/leagent/tools/base.py:81`).
2. Collapse double-write tools (`image_generate`, `screenshot`,
   `image_download`) to a single `register()`.
3. Begin retiring the heuristic `ArtifactRegistrar` path-scraping for tools that
   now return refs directly.

Exit criteria: P1 rows in §4.1 resolved; `ArtifactRegistrar` scraping only
covers legacy tools.

### Phase 2 — structural convergence

1. Move `services/database/` → `leagent/db/` with a re-export shim; update
   `alembic/env.py`.
2. Consolidate engine creation onto `leagent_core/db/make_async_engine()`
   (removes the duplicate SQLite-WAL / PG-pool setup).
3. Introduce per-domain repositories (`ChatRepository`, `FileRepository`,
   `TaskRepository`, `WorkflowExecutionRepository`) modeled on the existing
   `JobRepository` protocol in `backend/leagent/cron/repository.py`.
4. Resolve P2 doc-tool writes (scope decision per call site).
5. Decide session-state SSOT (§3.3) and remove the double-write path.

### Phase 3 — invariant hardening (see §6)

Graduate `test_invariants.py` from `pytest.xfail` waivers to strict,
merge-blocking assertions.

### Phase 4 — multi-instance readiness (optional)

`InMemoryPromptMap` → shared store; `CacheService` → Redis; `TieredSessionStore`
LRU as L1 only. Tracks API-review §6.1 (durable task queue for heavy work).

---

## 6. Invariant-Hardening Milestone

Graduate `backend/tests/test_file/test_invariants.py` from migration waivers
(`pytest.xfail`) to strict assertions that **block merges on violation**.

### 6.1 Current state

```68:85:backend/tests/test_file/test_invariants.py
    def test_no_direct_blob_writes(self):
        violations: list[str] = []
        for py, rel in _blob_path_files():
            if rel in self._SKIP_FILES:
                continue
            for i, line in enumerate(py.read_text().splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#") or stripped.startswith('"""'):
                    continue
                if self._WRITE_PAT.search(line):
                    violations.append(f"{rel}:{i}: {stripped}")

        if violations:
            pytest.xfail(
                "Direct file writes found in blob-layer code "
                "(expected during migration):\n"
                + "\n".join(violations[:10])
            )
```

- **INV-1** (no direct blob writes) — `pytest.xfail`. Soft.
- **INV-5** (`project/` never imports `FileService`/`FileRef`) — already a hard
  `assert`. Keep.
- **INV-7** (one containment check) — `pytest.xfail`. Soft.

### 6.2 Why a straight flip to `assert` is wrong

`_blob_path_files()` scans all of `services/`, `api/`, `tools/`, `cli/`,
`config/`, `workflow/`, `cron/`, `memory/`, etc. (it only excludes
`project/`, `code/`, `skills/`, and tests). A naive strict assertion would flag
the §4.3 legitimate config/CLI/log writes. Graduation therefore needs an
**explicit allowlist** plus **scope narrowing**, not just removing `xfail`.

### 6.3 Graduation mechanism

Replace the broad scan + `xfail` with a curated allowlist and a hard assert:

```python
# backend/tests/test_file/test_invariants.py  (proposed)

# Call sites that legitimately write non-managed-blob bytes.
# Each entry is "relative_path:line" and MUST carry a justification.
# Adding a new entry requires reviewer sign-off (see CODEOWNERS on this file).
_INV1_ALLOWLIST: dict[str, str] = {
    # infra / config
    "llm/provider_config.py:234": "provider config file, not a managed blob",
    "config/config.py:94": "app config file",
    "config/migrate_v2.py:157": "config migration",
    "config/migrate_v2.py:301": "config migration",
    "extensions/manager.py:72": "installed-extensions manifest",
    "workflow/io/serializer.py:27": "flow definition YAML",
    "workflow/io/serializer.py:29": "flow definition JSON",
    "cron/repository.py:366": "JSON job-repo atomic state file",
    "services/database/models/task.py:174": "append-mode task log",
    "memory/agent_memory.py:143": "append-only memory log",
    "tools/web/login.py:281": "tool-local session cookie cache",
    # cli/* writes config/exports — matched by prefix below
}
_INV1_ALLOWED_PREFIXES = ("cli/",)


class TestINV1_NoDirectWriteInBlobPaths:
    _SKIP_FILES = {"file/storage/local.py", "file/storage/backend.py"}
    _WRITE_PAT = re.compile(r"""open\([^)]*['"]w[ab]?['"]|\.write_bytes\(|\.write_text\(""")

    def test_no_direct_blob_writes(self):
        violations: list[str] = []
        for py, rel in _blob_path_files():
            if rel in self._SKIP_FILES:
                continue
            if any(rel.startswith(p) for p in _INV1_ALLOWED_PREFIXES):
                continue
            for i, line in enumerate(py.read_text().splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#") or stripped.startswith('"""'):
                    continue
                if self._WRITE_PAT.search(line):
                    key = f"{rel}:{i}"
                    if key in _INV1_ALLOWLIST:
                        continue
                    violations.append(f"{key}: {stripped}")

        assert not violations, (
            "Managed-blob bytes must be written via FileService.register(), "
            "not direct open()/write_bytes()/write_text(). "
            "If this is a non-blob write, add it to _INV1_ALLOWLIST with a "
            "justification:\n" + "\n".join(violations)
        )
```

Apply the same pattern to **INV-7**: replace `pytest.xfail` with `assert not
violations` plus an `_INV7_ALLOWLIST` for any remaining legitimate
`relative_to`/`commonpath` uses (target: empty after §5 Phase 2).

### 6.4 Sequencing the flip (no red CI)

The assertion can only flip green **after** the §4.1 P0/P1 violations are
migrated. Drive it down to zero before flipping:

1. **Phase 0 ends** → migrate P0 rows; allowlist shrinks to §4.3 entries only.
2. **Phase 1 ends** → migrate P1 rows; INV-1 violation count = 0 (modulo
   allowlist).
3. **Flip INV-1 to `assert`** in the same PR that lands the last P1 migration.
4. **Phase 2** drives INV-7 allowlist to empty, then **flip INV-7 to `assert`**.

### 6.5 Merge-blocking enforcement

1. Ensure these tests run in the default CI job (they are plain `pytest`, no
   special marker), so a violation fails the suite and blocks merge.
2. Add the invariant file to `CODEOWNERS` so allowlist edits require review.
3. Keep the justification string mandatory: an allowlist entry with no reason is
   itself a review-time red flag.
4. Document the rule in `AGENTS.md` (the "All managed blob writes go through
   `FileService.register()`" line already exists; link it to this milestone).

### 6.6 Exit criteria

- INV-1 and INV-7 are hard `assert`s; INV-5 unchanged.
- `_INV1_ALLOWLIST` contains only §4.3-class non-blob writes, each justified.
- `_INV7_ALLOWLIST` is empty.
- CI fails on any new ad-hoc managed-blob write or inline containment check.

---

## 7. Summary

| Deliverable | Outcome |
|---|---|
| Service-layer topology | `services/` is the thin application-service layer; capabilities live in `file/`/`code/`/`project/`/`db/`; routers get thin (addresses API-review §2.1, §4.3) |
| Ingress boundaries | One ingress per domain; Tier A (`FileService.register`) vs Tier B (project/code workspaces) never blur |
| Persistence recommendations | `StorageBackend` opaque-key contract; identity-vs-processing metadata split; immutable `FileScope`; session-state SSOT |
| Production-path audit | Every managed-blob write classified; P0/P1 migrations to `FileService.register()`; legitimate non-blob writes allowlisted |
| Invariant hardening | `test_invariants.py` graduates from `pytest.xfail` to merge-blocking `assert` with a justified allowlist, flipped only after violations reach zero |

Do **not** build a global "PersistenceService" — blob, SQL, vector, and mutable
FS have different semantics. Converge **within** each domain instead.
