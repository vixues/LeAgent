# Operations

This document covers deployment, one-time migrations, workers, and
monitoring of the workflow engine.

## Configuration (`workflow` section)

Defined in `leagent.config.settings.WorkflowEngineSettings`; set via the
`LEAGENT_WORKFLOW__*` env prefix or YAML config.

| Key                | Default      | Meaning                                           |
| ------------------ | ------------ | ------------------------------------------------- |
| `queue_backend`    | `memory`     | `memory` or `redis`.                              |
| `queue_url`        | `None`       | Redis URL when `queue_backend=redis`.             |
| `cache_mode`       | `classic`    | `none`, `classic`, `ram-pressure`, `lru`.         |
| `event_bus`        | `memory`     | `memory` or `redis` (pub/sub).                    |
| `event_bus_url`    | `None`       | Redis URL for pub/sub.                            |
| `custom_nodes_dir` | `None`       | Optional path for hot-reloadable custom nodes.    |
| `worker_concurrency` | `4`        | In-proc parallel nodes per worker.                |

## One-time data migration

If you are upgrading from a pre-canonical deployment, run the migration
script before starting the API server:

```bash
# Inside the backend container / venv:
python -m scripts.workflow.migrate_flows --dry-run     # preview
python -m scripts.workflow.migrate_flows --commit      # apply
python -m scripts.workflow.migrate_flows --scan-only   # audit
```

The script inlines a legacy → canonical upgrader (v1 list-based + v2
transitional payloads) and runs `io.load` + `io.validate` on the result.
Failures are printed with the offending flow id; fix them by hand and
re-run with `--commit`.

At boot `ServiceManager._assert_flows_canonical` runs the same checks in
the background and logs a warning if any stragglers remain — it is
non-fatal to avoid breaking local dev.

## Starting a worker

```bash
# Same process as the API (for dev): workers run inside ServiceManager.
python -m leagent

# Dedicated worker pool (for production):
python -m leagent.workflow.cli.workflow_worker \
    --concurrency 8 \
    --queue redis://redis:6379/0
```

Workers connect to the configured queue and event bus and register a
progress handler that fans events to the bus.

## Observability

- `POST /api/v1/workflow/admin/reload-nodes` — re-registers custom nodes
  after editing them on disk.
- `GET /api/v1/workflow/object_info` — exposes the registry snapshot so
  the frontend can render up-to-date node palettes.
- Progress events are emitted via `structlog`; pipe them to your log
  aggregator. Each frame carries `prompt_id`, `node_id`, and `type`.
- `scripts/workflow/queue_inspect.py` prints queue depth and the next
  `N` prompts for a quick sanity check.

## Troubleshooting

| Symptom                                            | Likely cause                        |
| -------------------------------------------------- | ----------------------------------- |
| `WorkflowLoaderError: canonical shape required`    | A flow row was written with a non-canonical document; run the migration script. |
| Boot warning `Found N non-canonical Flow.data rows`| Same — background canonical check tripped. |
| Nodes missing from `/object_info`                  | Custom-nodes directory not configured or failed to import; check logs, POST to reload endpoint. |
| Runs stuck in `queued`                             | No worker attached to the configured queue. |
| WebSocket disconnects immediately                  | Auth middleware is rejecting the handshake; pass the JWT in a cookie or `Authorization` header. |
