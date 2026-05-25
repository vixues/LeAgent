export type ProviderType = 'openai' | 'anthropic' | 'qwen' | 'ollama' | 'custom' | 'dashscope' | 'azure' | 'deepseek' | 'vllm';

export interface ProviderModelInfo {
  name: string;
  tier: string;
  context_window: number;
  enabled?: boolean;
  description?: string;
  price_input_per_1m?: number;
  price_output_per_1m?: number;
  supports_tools?: boolean | null;
  supports_vision?: boolean | null;
}

export interface ModelUsageRow {
  model: string;
  request_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  avg_latency_ms: number;
  total_cost_usd?: number;
  last_used_at: string | null;
}

export interface UsageSummary {
  days: number;
  since: string;
  total_requests: number;
  total_tokens: number;
  total_cost_usd?: number;
  cache_hit_rate?: number;
  avg_latency_ms: number;
  rows: ModelUsageRow[];
}

export interface ProviderHealthEntry {
  provider_name: string;
  is_healthy: boolean | null;
  latency_ms?: number;
  ttfb_ms?: number;
  status?: string;
  error?: string | null;
  error_category?: string | null;
  last_checked?: number | null;
  circuit?: Record<string, unknown>;
}

export interface DeepSeekBalanceInfo {
  currency: string;
  total_balance: string;
  granted_balance: string;
  topped_up_balance: string;
}

export interface DeepSeekBalanceResponse {
  provider_name: string;
  is_available: boolean;
  balance_infos: DeepSeekBalanceInfo[];
  balance_items?: Array<{ label: string; amount: string; currency?: string; usage_percent?: number | null }>;
  last_queried?: string;
}

/** Admin system status (GET /api/v1/health/detailed). */
export interface SystemDetailedHealth {
  status: string;
  version: string;
  uptime_seconds: number;
  components?: Record<string, Record<string, unknown>>;
}

/** Admin version payload (GET /api/v1/health/version). */
export interface SystemVersionPayload {
  version: string;
  api_version?: string;
  build?: string;
  python_version?: string;
}

export type SystemMetricsPayload = Record<string, unknown>;

export interface ModelProvider {
  name: string;
  type: ProviderType;
  label: string;
  enabled: boolean;
  base_url: string;
  /** From preset; false for e.g. Ollama local providers that do not use API keys. */
  requires_api_key?: boolean;
  api_key_set: boolean;
  models: ProviderModelInfo[];
  supports_streaming: boolean;
  supports_tools: boolean;
  supports_embeddings: boolean;
  is_healthy: boolean | null;
  timeout: number;
  metadata: Record<string, unknown>;
}

export interface ModelProviderFormData {
  name: string;
  type: ProviderType;
  base_url?: string;
  api_key?: string;
  models?: Array<{
    name: string;
    tier?: string;
    context_window?: number;
    enabled?: boolean;
    description?: string;
    price_input_per_1m?: number;
    price_output_per_1m?: number;
    supports_tools?: boolean | null;
    supports_vision?: boolean | null;
  }>;
  enabled: boolean;
  timeout?: number;
  metadata?: Record<string, unknown>;
  extra?: Record<string, unknown>;
}

export interface DefaultModelConfig {
  provider: string;
  model: string;
}

export interface PresetInfo {
  type: string;
  label: string;
  default_base_url: string;
  requires_api_key: boolean;
  models: ProviderModelInfo[];
}

export interface TestResult {
  provider_name: string;
  model: string;
  is_healthy: boolean;
  latency_ms: number;
  ttfb_ms?: number;
  status?: string;
  error_category?: string | null;
  error?: string;
}

export interface DiscoveredModel {
  id: string;
  name: string;
  owned_by?: string;
  created?: unknown;
  already_configured: boolean;
  raw?: Record<string, unknown>;
}

export interface ProviderUsageRow {
  provider_name: string;
  request_count: number;
  total_tokens: number;
  total_cost_usd: number;
  avg_latency_ms: number;
}

export interface RequestLogRow {
  id: string;
  provider_name: string;
  model: string;
  request_model: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  total_cost_usd: number;
  latency_ms: number;
  ttfb_ms: number;
  status_code: number;
  error?: string | null;
  is_streaming: boolean;
  created_at: string;
}

export interface UsageTrendRow {
  bucket: string;
  request_count: number;
  total_tokens: number;
  total_cost_usd: number;
}

export interface PricingEntry {
  model: string;
  input_per_1m: number;
  output_per_1m: number;
  cache_read_per_1m?: number;
  cache_write_per_1m?: number;
}

export interface SpeedTestResult {
  url: string;
  ok: boolean;
  latency_ms: number;
  error?: string;
}

export interface SpendLimitStatus {
  provider_name: string;
  daily_limit_usd?: number | null;
  monthly_limit_usd?: number | null;
  daily_spend_usd: number;
  monthly_spend_usd: number;
  daily_exceeded: boolean;
  monthly_exceeded: boolean;
}

export type ToolCategory =
  | 'doc'
  | 'web'
  | 'data'
  | 'gen'
  | 'integration'
  | 'util'
  | 'canvas'
  | 'workflow'
  | 'code'
  | 'skills';

export interface Tool {
  id: string;
  name: string;
  description: string;
  category: ToolCategory;
  version: string;
  timeout_sec: number;
  max_retries: number;
  requires_gpu: boolean;
  enabled: boolean;
  config: Record<string, unknown>;
}

export interface ToolDetail extends Tool {
  parameters: Record<string, unknown>;
}

export interface ToolConfig {
  toolId: string;
  config: Record<string, unknown>;
}

export interface RuleSetInfo {
  id: string;
  name: string;
  description?: string;
  enabled: boolean;
  rule_count: number;
  tags: string[];
}

export interface RuleSetDetail {
  id: string;
  name: string;
  description?: string;
  enabled: boolean;
  version: string;
  rules: Array<Record<string, unknown>>;
  tags: string[];
}

export interface RuleSetCreateData {
  id: string;
  name: string;
  description?: string;
  enabled?: boolean;
  rules?: Array<Record<string, unknown>>;
  tags?: string[];
}

export interface RuleSetUpdateData {
  name?: string;
  description?: string;
  enabled?: boolean;
  rules?: Array<Record<string, unknown>>;
  tags?: string[];
}

export interface RuleEvaluateResponse {
  rule_set_id: string;
  passed: boolean;
  total_rules: number;
  error_count: number;
  warning_count: number;
  info_count: number;
  execution_time_ms: number;
  results: Array<Record<string, unknown>>;
}

/** @deprecated - kept for backward compat; prefer RuleSetInfo */
export interface Rule {
  id: string;
  name: string;
  description: string;
  condition: string;
  action: string;
  priority: number;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

/** @deprecated */
export interface RuleFormData {
  name: string;
  description: string;
  condition: string;
  action: string;
  priority: number;
  enabled: boolean;
}

export type UserRole = 'admin' | 'dept_head' | 'staff' | 'readonly';
export type UserStatus = 'active' | 'inactive' | 'suspended';

export interface User {
  id: string;
  username: string;
  email?: string;
  full_name?: string;
  role: UserRole;
  status: UserStatus;
  department?: string;
  avatar_url?: string;
  is_superuser: boolean;
  last_login_at?: string;
  login_count: number;
  created_at: string;
  updated_at: string;
}

export interface UserFormData {
  username: string;
  email?: string;
  password?: string;
  full_name?: string;
  role: UserRole;
  department?: string;
}

export type TaskStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'killed'
  | 'timeout';

export type TaskType =
  | 'agent'
  | 'shell'
  | 'workflow'
  | 'tool'
  | 'batch'
  | 'dream';

export type TaskPriority = 'low' | 'normal' | 'high' | 'urgent';
export type RuntimeProfile = 'standard' | 'coding_long' | 'coding_extended';

export interface AgentRunRequest {
  message: string;
  session_id?: string | null;
  name?: string;
  description?: string | null;
  runtime_profile?: RuntimeProfile;
  prompt_variant?: string;
  model_tier?: string;
  project_roots?: string[];
  authorized_roots?: string[];
  max_turns?: number;
  max_tool_calls_per_turn?: number;
  priority?: TaskPriority;
  timeout_seconds?: number;
}

export interface AgentRunResponse {
  task_id: string;
  session_id?: string | null;
  status: TaskStatus;
  runtime_profile: RuntimeProfile;
  output_offset: number;
}

export interface Task {
  id: string;
  name: string;
  description?: string | null;
  task_type: TaskType;
  status: TaskStatus;
  priority: TaskPriority;
  progress: number;
  progress_message?: string | null;
  user_id?: string | null;
  session_id?: string | null;
  flow_id?: string | null;
  parent_id?: string | null;
  error?: string | null;
  output_file?: string | null;
  duration_ms?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskOutputChunk {
  task_id: string;
  output: string;
  bytes_read: number;
  next_offset: number;
  status: TaskStatus;
  is_done: boolean;
}

export interface TaskLog {
  timestamp: string;
  level: 'info' | 'warn' | 'error';
  message: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface ApiKeyInfo {
  id: string;
  name: string;
  key: string;
  maskedKey: string;
  createdAt: string;
  lastUsedAt?: string;
  expiresAt?: string;
}
