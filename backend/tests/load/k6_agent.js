// k6 scenario: sustained load on the Agent Runtime's streaming endpoint.
// Uses HTTP (Gateway SSE/WS) for portability; swap to gRPC with xk6-grpc
// once the target deploy exposes Agent Runtime gRPC directly.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const p95 = new Trend('p95_latency');
const failures = new Rate('failures');

export const options = {
  scenarios: {
    steady: {
      executor: 'constant-arrival-rate',
      rate: 50,
      timeUnit: '1s',
      duration: '2m',
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
  thresholds: {
    p95_latency: ['p(95)<750'],
    failures: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.LEAGENT_BASE_URL || 'http://localhost:8000';
const TOKEN = __ENV.LEAGENT_TOKEN || '';

export default function () {
  const res = http.post(
    `${BASE_URL}/api/v1/chat`,
    JSON.stringify({ message: 'hello k6', session_id: __VU + '-' + __ITER }),
    {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${TOKEN}`,
      },
    }
  );
  p95.add(res.timings.duration);
  failures.add(res.status >= 500);
  check(res, { 'status 2xx': (r) => r.status >= 200 && r.status < 300 });
  sleep(0.1);
}
