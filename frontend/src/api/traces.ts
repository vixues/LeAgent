import { apiClient } from './client';

export interface TraceSummary {
  trace_id: string;
  parent_trace_id?: string | null;
  session_id?: string | null;
  user_id?: string | null;
  scope: string;
  agent_name: string;
  model: string;
  status: string;
  terminal_reason?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_miss_tokens: number;
  total_cost_usd: number;
  tool_call_count: number;
  llm_call_count: number;
  experiment_id?: string | null;
  prompt_hash?: string | null;
  tags?: unknown;
  error?: string | null;
  scores?: unknown;
  root_span_id?: string | null;
}

export interface TraceSpan {
  span_id: string;
  parent_span_id?: string | null;
  trace_id: string;
  seq: number;
  kind: string;
  name: string;
  status: string;
  started_at?: string | null;
  ended_at?: string | null;
  latency_ms: number;
  attrs?: Record<string, unknown> | null;
  input_preview?: string | null;
  output_preview?: string | null;
  payload_ref?: string | null;
  children?: TraceSpan[];
}

export interface TraceDetail {
  trace: TraceSummary;
  spans: TraceSpan[];
  tree: TraceSpan[];
}

export interface ModelTraceStats {
  model: string;
  runs: number;
  successes: number;
  errors: number;
  success_rate: number;
  avg_latency_ms: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  avg_input_tokens: number;
  avg_output_tokens: number;
  avg_cost_usd: number;
  avg_tool_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
}

export interface TraceExperiment {
  experiment_id: string;
  name: string;
  prompt: string;
  session_id?: string | null;
  model_ids: string[];
  created_by?: string | null;
  status: string;
  error?: string | null;
  created_at?: string | null;
  traces: TraceSummary[];
}

export const tracesApi = {
  list: (params?: {
    session_id?: string;
    model?: string;
    status?: string;
    experiment_id?: string;
    has_error?: boolean;
    limit?: number;
    offset?: number;
  }) => apiClient.get<TraceSummary[]>('/traces', params),

  get: (traceId: string) => apiClient.get<TraceDetail>(`/traces/${traceId}`),

  spans: (traceId: string) => apiClient.get<TraceSpan[]>(`/traces/${traceId}/spans`),

  exportUrl: (traceId: string) => `/api/v1/traces/${traceId}/export`,

  exportJsonl: async (traceId: string): Promise<string> => {
    const res = await fetch(`/api/v1/traces/${encodeURIComponent(traceId)}/export`, {
      credentials: 'include',
    });
    if (!res.ok) throw new Error(`export failed: ${res.status}`);
    return res.text();
  },

  statsByModel: (days = 30) =>
    apiClient.get<ModelTraceStats[]>('/traces/stats/by-model', { days }),

  listSession: (sessionId: string, limit = 20) =>
    apiClient.get<TraceSummary[]>(`/chat/sessions/${sessionId}/traces`, { limit }),

  listExperiments: (limit = 50) =>
    apiClient.get<TraceExperiment[]>('/traces/experiments', { limit }),

  createExperiment: (body: {
    name?: string;
    prompt: string;
    model_ids: string[];
    session_id?: string;
    agent_name?: string;
  }) => apiClient.post<TraceExperiment>('/traces/experiments', body),

  getExperiment: (id: string) =>
    apiClient.get<TraceExperiment>(`/traces/experiments/${id}`),

  runExperiment: (id: string, agentName = 'default_agent') =>
    apiClient.post<TraceExperiment>(
      `/traces/experiments/${id}/run`,
      undefined,
      { params: { agent_name: agentName } },
    ),
};
