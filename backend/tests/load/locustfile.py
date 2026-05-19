"""Locust profile covering the main HTTP surface of the API Gateway.

Run: ``locust -f tests/load/locustfile.py --host=http://localhost:8000``.

Environment:

* ``LEAGENT_TOKEN`` — bearer token used for every request. Required.
* ``LEAGENT_FLOW_ID`` — a flow id to invoke; optional.
* ``LEAGENT_TOOL`` — a tool name to invoke; default ``echo``.
"""

from __future__ import annotations

import json
import os
import random
import string
from typing import Any

from locust import HttpUser, between, events, task


TOKEN = os.getenv("LEAGENT_TOKEN", "")
FLOW_ID = os.getenv("LEAGENT_FLOW_ID")
TOOL_NAME = os.getenv("LEAGENT_TOOL", "echo")


def _rand(n: int = 16) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


class LeAgentUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        if not TOKEN:
            events.quitting.fire(environment=self.environment)
            raise RuntimeError("LEAGENT_TOKEN env var is required")
        self.client.headers["Authorization"] = f"Bearer {TOKEN}"
        self.client.headers["x-request-id"] = _rand()

    # ---- realistic weighted mix ----
    @task(5)
    def chat(self) -> None:
        payload: dict[str, Any] = {
            "message": "hello " + _rand(4),
            "session_id": _rand(),
        }
        with self.client.post("/api/v1/chat", json=payload,
                               catch_response=True, name="POST /chat") as r:
            if r.status_code >= 500:
                r.failure(f"5xx: {r.status_code}")

    @task(2)
    def flow_execute(self) -> None:
        if not FLOW_ID:
            return
        payload = {"flow_id": FLOW_ID, "inputs": {"text": _rand(8)}}
        self.client.post("/api/v1/flows/execute", json=payload,
                          name="POST /flows/execute")

    @task(2)
    def tool_invoke(self) -> None:
        payload = {"name": TOOL_NAME, "arguments": {"text": _rand(16)}}
        self.client.post("/api/v1/tools/invoke", json=payload,
                          name="POST /tools/invoke")

    @task(1)
    def upload(self) -> None:
        blob = ("x" * 1024).encode()
        self.client.post(
            "/api/v1/files/upload",
            files={"file": ("load.txt", blob, "text/plain")},
            name="POST /files/upload",
        )

    @task(3)
    def health(self) -> None:
        self.client.get("/health", name="GET /health")


# --- CI gate -----------------------------------------------------------------

_P95_BUDGET_MS = 750.0
_ERROR_BUDGET = 0.01


@events.quitting.add_listener
def _enforce_gates(environment: Any, **_: Any) -> None:
    """Post-run gate used by ``ci-perf.sh``."""
    stats = environment.stats.total
    if stats.num_requests == 0:
        return
    p95 = stats.get_response_time_percentile(0.95)
    error_rate = stats.num_failures / max(1, stats.num_requests)
    summary = {
        "rps": stats.total_rps,
        "p95_ms": p95,
        "error_rate": error_rate,
    }
    out = os.getenv("LEAGENT_LOCUST_SUMMARY")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)

    if p95 > _P95_BUDGET_MS or error_rate > _ERROR_BUDGET:
        environment.process_exit_code = 1
        events.request.fire(
            request_type="PERF_GATE",
            name="ci-gate",
            response_time=p95,
            response_length=0,
            exception=AssertionError(
                f"perf gate violated: p95={p95:.1f}ms (budget={_P95_BUDGET_MS}), "
                f"errors={error_rate:.3%} (budget={_ERROR_BUDGET:.1%})"
            ),
            context={},
        )
