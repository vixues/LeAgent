# AST / LSP tooling vs `project_apply_patch` (boundary note)

LeAgent’s coding toolbox is intentionally centred on **textual, on-disk truth** and **unified diffs**, not on shipping whole projects through the model as opaque blobs.

## What exists today

- **`project_apply_patch`** — applies a unified diff produced the same way as `git diff`. Best for multi-hunk / multi-file edits when the model can name exact context lines.
- **`project_edit`** — uniqueness-checked substring replace; best for surgical single-location edits.
- **`project_outline`** (Python) — lightweight top-level defs / classes / imports for navigation; **not** a full symbol table or ref-index.
- **`syntax_validator`** — parse-only JSON / Python / TOML / YAML / JSONC checks with line/column diagnostics.

Together these cover **diff-first workflows** and **cheap structural hints** without running a language server in-process.

## What an AST / LSP layer would add

- Cross-file **rename** and **find references** with correctness guarantees.
- **Typed** edits (e.g. only rename a binding, not a shadowed string with the same spelling).
- IDE-grade refactorings driven by compiler/LSP semantics.

## When *not* to add LSP in this codebase (yet)

- **Operational cost** — per-language servers, workspace roots, version skew with user toolchains, and resource limits in the agent process.
- **Overlap** — for many repo edits, a correct unified diff after `project_read` is smaller and easier to audit than AST JSON patches.
- **Security / sandbox** — LSP often expects a full workspace and long-lived processes; the current `project_shell` + diff loop stays simpler to harden.

## Recommended split

| Goal | Prefer |
|------|--------|
| Multi-file feature work | `project_read` → `project_apply_patch` or small `project_edit` steps |
| Locate symbols quickly (Python) | `project_outline` + `project_grep` |
| Prove syntax before write | `syntax_validator` |
| Rename across codebase with semantic safety | External IDE / future dedicated `project_lsp_*` tools (not implemented here) |

If we later add AST-backed tools, they should **compose with** `project_apply_patch` (e.g. LSP proposes edits, still materialised as patches on disk) rather than replacing the filesystem as the source of truth.
