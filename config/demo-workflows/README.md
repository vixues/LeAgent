# Demo workflows (canonical YAML)

These files are **canonical** workflow documents (`nodes` as a map, `class_type`, `control.start` / `control.end`). They use only built-in tools that work with **public HTTP APIs** (no Bing/Google keys required for the Wikipedia path).

| File | Purpose |
|------|---------|
| `demo-news-public.yaml` | `web_search` with `focus=wikipedia` — good for quick demos. |
| `demo-fx-rates-public.yaml` | Frankfurter ECB FX JSON via `web_scraper` + `json_parser` — “dashboard” style structured output. |

## Import

From the repo `backend/` directory:

```bash
uv run python -m scripts.workflow.import_demo_flows
```

The script prints each new `flow_id` (UUID). Use that value when creating a **Cron** job of type **workflow** so scheduled runs execute the **same** graph as manual **Run** in the UI.

Options:

- `--dir /path/to/dir` — override the YAML directory (default: this folder).
- `--user-id <uuid>` — flow owner (default: local dev user).
- `--no-skip-existing` — create duplicates even if a flow with the same name exists.

REST equivalent: `POST /api/v1/workflow/flows/import` with `document` = parsed YAML/JSON body (see [workflow engine docs](../../backend/docs/workflow-engine/demo-flows-and-cron.md)).
