# Workflow utility scripts

One-off and operational helpers for the workflow engine. All scripts live
under `backend/scripts/workflow/` and run from the backend venv.

## `migrate_flows.py`

One-shot migration of existing `Flow.data` rows to the canonical workflow
schema. The engine does **not** perform on-read schema upgrades, so this
script must be run once per environment when upgrading from a pre-canonical
deployment.

```bash
# Preview (default): no DB writes, prints a per-row summary.
python -m scripts.workflow.migrate_flows --dry-run

# Apply: writes canonical JSON back to each Flow.data row.
python -m scripts.workflow.migrate_flows --commit

# Audit only: list rows that are not already canonical without
# attempting conversion.
python -m scripts.workflow.migrate_flows --scan-only

# Limit scope (useful when fixing a handful of rows by hand).
python -m scripts.workflow.migrate_flows --dry-run --limit 5

# Backfill the UI layout block (``data.ui``) for existing rows so
# the canvas renders an overlap-free topology the first time they
# open. Also upgrades legacy rows if any are still around.
python -m scripts.workflow.migrate_flows --relayout --commit
```

Exit code `0` means everything validated; non-zero means at least one
row failed to upgrade. Check the structured log lines for per-row detail.

## `queue_inspect.py`

Prints the depth of the configured `PromptQueue` and the next N pending
prompts, respecting priority order. Useful to verify that a worker pool is
keeping up.

```bash
python -m scripts.workflow.queue_inspect --limit 20
```

## `audit_nodes.py`

Dumps the node registry and any configured `NodeReplaceRegistry` entries in
a compact table. Handy when reviewing which nodes a tenant can actually use
after a deploy.

```bash
python -m scripts.workflow.audit_nodes
```

## `import_demo_flows.py`

Imports canonical demo YAML from `config/demo-workflows/` into the `flows`
table (same as `POST /api/v1/workflow/flows/import`). Prints new `flow_id`
values for wiring Cron jobs.

```bash
uv run python -m scripts.workflow.import_demo_flows
```
