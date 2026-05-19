#!/usr/bin/env bash
# CI performance gate — 50 RPS / 2 min smoke with p95 + error budget.
# Exit non-zero if either budget is exceeded.

set -euo pipefail

HOST="${LEAGENT_HOST:-http://localhost:8000}"
TOKEN="${LEAGENT_TOKEN:-}"
REPORT_DIR="${REPORT_DIR:-reports}"

mkdir -p "$REPORT_DIR"

echo "[ci-perf] running Locust against $HOST"
LEAGENT_LOCUST_SUMMARY="$REPORT_DIR/locust_summary.json" \
LEAGENT_TOKEN="$TOKEN" \
locust -f "$(dirname "$0")/locustfile.py" \
  --host="$HOST" \
  --users=50 --spawn-rate=10 --run-time=2m \
  --headless \
  --csv="$REPORT_DIR/locust" \
  --exit-code-on-error 1 \
  --only-summary

echo "[ci-perf] gate summary:"
cat "$REPORT_DIR/locust_summary.json"
