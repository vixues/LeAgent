# LeAgent load-test harness

Two harnesses live here:

| Tool   | Scope                                                                 | Entrypoint                    |
| ------ | --------------------------------------------------------------------- | ----------------------------- |
| Locust | HTTP: `/api/v1/chat`, `/api/v1/flows/execute`, `/api/v1/tools/invoke`, `/upload` | `locustfile.py`              |
| k6     | gRPC: Agent Runtime `Stream`, LLM Gateway `Complete`                  | `k6_agent.js`, `k6_llm.js`    |

## Running locally

```bash
# HTTP profile (web-like mix)
pip install locust
locust -f tests/load/locustfile.py --host=http://localhost:8000 \
  --users=200 --spawn-rate=20 --run-time=2m --headless \
  --csv=reports/locust

# gRPC profile
k6 run tests/load/k6_agent.js \
  --vus=50 --duration=2m \
  --summary-export=reports/k6_agent.json
```

## CI performance gates

`ci-perf.sh` runs the 50 RPS / 2 min smoke and asserts both gates:

* p95 HTTP latency ≤ **750 ms**
* error rate ≤ **1%**

Baselines captured from the monolith live at
`tests/load/baselines/monolith.json`. The target after the microservices
rollout is ≥5× throughput at equal p95.
