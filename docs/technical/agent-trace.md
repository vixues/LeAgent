# Agent Running Trace

Durable **debug / eval** telemetry for agent turns. This plane is separate from:

| Plane | Purpose | Owner |
|-------|---------|-------|
| Chat transcript | User-visible SSOT | `TieredSessionStore` |
| Resume | Pause / continue | `CheckpointStore` |
| **Running trace** | Evaluation, model comparison, bug localization | `leagent.telemetry.trace` |

Inspired by Hermes (OTel / OpenInference span kinds), Codex (`trace.jsonl` + out-of-line payloads), and Claude session transcripts (append-only events).

## Capture

- `begin_execution` / `end_execution*` open and close the root `agent` span (`trace_id` = `run_id`).
- `run_loop` appends tool / result / error spans from `AgentEvent`s (observer-only).
- `TraceHook` records compact / subagent boundaries.
- `LLMService._record_request_log` writes `llm_request_logs.run_id` and an `llm` span.

## Settings

| Env | Default | Meaning |
|-----|---------|---------|
| `LEAGENT_TRACE__ENABLED` | `true` | Master switch |
| `LEAGENT_TRACE__CAPTURE_PAYLOADS` | `false` | Write full I/O under `LEAGENT_HOME/traces/` |
| `LEAGENT_TRACE__PREVIEW_CHARS` | `4096` | Truncated preview length |
| `LEAGENT_TRACE__RETENTION_DAYS` | `30` | Intended retention (cleanup job TBD) |

## API

- `GET /api/v1/traces` — list / filter
- `GET /api/v1/traces/{id}` — summary + span tree
- `GET /api/v1/traces/{id}/export` — Codex-style JSONL
- `GET /api/v1/traces/stats/by-model` — aggregate scorecard
- `POST /api/v1/traces/experiments` + `/run` — same-prompt multi-model compare
- `GET /api/v1/chat/sessions/{id}/traces` — session-scoped list

## UI

- Chat execution panel: run waterfall + JSONL export
- Admin → **Agent Traces**: runs list, by-model stats, compare experiments
