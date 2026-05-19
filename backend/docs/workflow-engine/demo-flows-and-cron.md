# Demo flows and scheduled jobs

This project ships **canonical** demo workflow YAML under
[`config/demo-workflows/`](../../../config/demo-workflows/) at the repository root.
They are meant to run on a normal single-machine install: public HTTP only (no Bing/Google
key for the Wikipedia demo path), and outputs you can read from **workflow execution**
history in the UI.

## What is included

| File | Tools | Notes |
|------|--------|------|
| `demo-news-public.yaml` | `web_search` (`focus=wikipedia`) | Uses the Wikipedia API path inside `web_search`; good when `WEB_SEARCH_PROVIDER` is unset. |
| `demo-fx-rates-public.yaml` | `web_scraper`, `json_parser` | Fetches ECB **Frankfurter** `latest` JSON (no API key). Requires Chromium/Playwright (same as PDF export / browser tools). |

## Importing into the database

**CLI (recommended for local dev)**

From `backend/`:

```bash
uv run python -m scripts.workflow.import_demo_flows
```

The command prints each new **`flow_id` (UUID)**. Re-run skips flows that already exist with the same **name** unless you pass `--no-skip-existing`.

**HTTP API**

`POST /api/v1/workflow/flows/import` with a JSON body:

```json
{
  "name": "My copy of demo news",
  "document": { "...": "canonical workflow dict or list accepted by load()" }
}
```

See [`api-reference.md`](api-reference.md) for the full contract.

## Aligning Cron with manual “Run”

Both paths load the **same** row from the `flows` table by primary key UUID:

- Manual run: `POST /api/v1/workflow/flows/{flow_id}/run`
- Cron (workflow target): `workflow_id` / `target_id` on the job = that same **`flow_id`**

The engine definition is always `Flow.data` loaded via [`FlowWorkflowRegistry.get`](../../leagent/workflow/registry.py). Put **payload keys** on the cron job that match the workflow’s declared **`inputs`** (for example `topic`, `base`, `targets`) so scheduled runs behave like the playground with different parameters.

**Example (conceptual)** after import printed `flow_id=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee`:

- Schedule: `0 * * * *` (hourly) for a smoke test, or `*/15 * * * *` only on lab machines.
- Payload:

```json
{
  "topic": "Inflation",
  "base": "EUR",
  "targets": "USD,CNY"
}
```

Use a modest cadence to avoid rate limits and unnecessary Playwright load on `web_scraper`.

## `WEB_FETCH` and robots.txt

`web_scraper` checks [`assert_fetch_allowed`](../../leagent/tools/web/scraper.py) before navigation. If a host’s `robots.txt` disallows the URL, the tool fails open only where the policy says so; in restricted environments you may need to:

- Prefer the **Wikipedia-only** demo when Playwright or outbound HTTP is constrained.
- Tune `WEB_FETCH_*` settings (see root `AGENTS.md` / `Settings`) for development; do not disable politeness on production multi-tenant systems without an ops review.

## Tests

`tests/test_demo_workflows.py` loads each `demo-*.yaml`, runs `validate()` with the real node registry, and asserts the graph is accepted. It does **not** call the public internet (no flaky CI).
