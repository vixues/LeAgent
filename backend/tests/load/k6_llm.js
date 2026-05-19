// k6 scenario: LLM Gateway completion load.

import http from 'k6/http';
import { check } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const latency = new Trend('llm_latency');
const failures = new Rate('llm_failures');

export const options = {
  vus: 30,
  duration: '2m',
  thresholds: {
    llm_latency: ['p(95)<2500'],
    llm_failures: ['rate<0.02'],
  },
};

const BASE_URL = __ENV.LEAGENT_BASE_URL || 'http://localhost:8000';
const TOKEN = __ENV.LEAGENT_TOKEN || '';

export default function () {
  const res = http.post(
    `${BASE_URL}/api/v1/llm/complete`,
    JSON.stringify({
      model: __ENV.LEAGENT_MODEL || 'gpt-4o-mini',
      messages: [
        { role: 'system', content: 'Reply with a single word.' },
        { role: 'user', content: 'ping' },
      ],
      max_tokens: 8,
    }),
    {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${TOKEN}`,
      },
    }
  );
  latency.add(res.timings.duration);
  failures.add(res.status >= 500);
  check(res, { 'status 2xx': (r) => r.status >= 200 && r.status < 300 });
}
