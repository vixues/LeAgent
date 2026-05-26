# LeAgent Benchmark Guide

This guide documents the lightweight chat streaming benchmark in
`scripts/perf_benchmark.py`.

## Prerequisites

- Start the backend locally so `http://localhost:7860/api/v1` is reachable.
- Run commands from the backend project with `uv`:

```bash
cd backend
uv run python ../scripts/perf_benchmark.py --requests 5 --concurrency 3
```

The harness uses only Python stdlib modules, but `uv run` keeps execution
consistent with the backend environment.

## Common Runs

Smoke test:

```bash
cd backend
uv run python ../scripts/perf_benchmark.py \
  --requests 1 \
  --concurrency 1 \
  --timeout 30 \
  --message "Perf smoke request {i}: respond with OK."
```

Small baseline:

```bash
cd backend
uv run python ../scripts/perf_benchmark.py \
  --requests 5 \
  --concurrency 3 \
  --timeout 120 \
  --new-session-per-request \
  --message "Benchmark turn {i}: answer 2+2 in one short sentence." \
  --output ../scripts/perf_latest.json
```

Slow-consumer backpressure test:

```bash
cd backend
uv run python ../scripts/perf_benchmark.py \
  --requests 2 \
  --concurrency 2 \
  --timeout 120 \
  --slow-consumer-ms 50 \
  --new-session-per-request \
  --message "Slow consumer test {i}: say hello." \
  --output ../scripts/perf_slow_consumer.json
```

Custom backend URL:

```bash
cd backend
uv run python ../scripts/perf_benchmark.py \
  --base-url http://localhost:7860/api/v1 \
  --requests 10 \
  --concurrency 5
```

## Output

The benchmark prints JSON and optionally writes it with `--output`.

Important fields:

- `summary.success_rate`: request success ratio.
- `summary.first_event_ms`: time to first non-empty SSE line. This is the
  closest harness-level proxy for chat perceived responsiveness.
- `summary.total_ms`: total streaming duration.
- `elapsed_ms`: wall-clock time for the full benchmark batch.
- `samples[].bytes_read`: approximate stream payload size.
- `samples[].error`: transport or HTTP error details.

Example result from a local run:

```json
{
  "requests": 5,
  "success": 5,
  "error": 0,
  "success_rate": 1.0,
  "first_event_ms": {
    "p50": 156.9,
    "p95": 182.7,
    "p99": 182.7
  },
  "total_ms": {
    "p50": 3813.0,
    "p95": 4860.4,
    "p99": 4860.4
  }
}
```

## Interpreting Results

- Track `first_event_ms` for user-perceived chat latency regressions.
- Track `total_ms` for provider generation speed and end-to-end streaming
  overhead.
- Use `--new-session-per-request` to stress session creation and first-turn
  setup. The harness omits `session_id` in this mode so the API creates an
  owned session with the authenticated local user.
- Use `--session-id` only with an existing chat session UUID. Sending an
  arbitrary UUID can make the stream response succeed while later persistence
  fails foreign-key checks.
- Use `--slow-consumer-ms` to validate stream queue backpressure behavior.

For deeper diagnosis, compare benchmark output with Prometheus metrics such as
`leagent_llm_stream_ttfb_seconds`,
`leagent_agent_turn_phase_duration_seconds`,
`leagent_db_query_duration_seconds`, and
`leagent_agent_stream_queue_depth_observed`.

## Notes

- Results depend heavily on the configured LLM provider, model, network, and
  prompt length.
- Keep baseline JSON files in `scripts/` only when they are useful for
  comparing a specific optimization.
- Prefer short, deterministic prompts when measuring framework overhead.
