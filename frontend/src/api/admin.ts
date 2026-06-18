import { apiClient } from './client';
import type {
  ModelProvider,
  ModelProviderFormData,
  DefaultModelConfig,
  PresetInfo,
  TestResult,
  Tool,
  ToolConfig,
  RuleSetInfo,
  RuleSetDetail,
  RuleSetCreateData,
  RuleSetUpdateData,
  RuleEvaluateResponse,
  User,
  UserFormData,
  Task,
  PaginatedResponse,
  ApiKeyInfo,
  UsageSummary,
  ProviderHealthEntry,
  DeepSeekBalanceResponse,
  DiscoveredModel,
  ProviderUsageRow,
  RequestLogRow,
  UsageTrendRow,
  PricingEntry,
  SpeedTestResult,
  SpendLimitStatus,
  AvailableModel,
  ImageGenPreset,
  ImageGenDefault,
  ImageGenBackend,
  ImageGenCredentialStatus,
  ImageGenCredentialUpdate,
  ImageGenLocalConfig,
  ImageGenTestRequest,
  ImageGenTestResult,
  ImageGenCustomProvider,
  ImageGenCustomProviderUpdate,
} from '@/types/admin';

export const adminApi = {
  providers: {
    list: () => apiClient.get<ModelProvider[]>('/models/providers'),
    get: (name: string) => apiClient.get<ModelProvider>(`/models/providers/${name}`),
    create: (data: ModelProviderFormData) => apiClient.post<ModelProvider>('/models/providers', data),
    update: (name: string, data: Partial<ModelProviderFormData>) =>
      apiClient.put<ModelProvider>(`/models/providers/${name}`, data),
    delete: (name: string) => apiClient.delete(`/models/providers/${name}`),
    test: (name: string) => apiClient.post<TestResult>(`/models/providers/${name}/test`),
    health: (name: string) => apiClient.get<TestResult>(`/models/providers/${name}/health`),
    balance: (name: string) => apiClient.get<DeepSeekBalanceResponse>(`/models/providers/${name}/balance`),
    discover: (name: string) => apiClient.get<DiscoveredModel[]>(`/models/providers/${name}/discover`),
    speedTest: (name: string, candidates: string[]) =>
      apiClient.post<SpeedTestResult[]>(`/models/providers/${name}/speed-test`, { candidates }),
    limits: (name: string) => apiClient.get<SpendLimitStatus>(`/models/providers/${name}/limits`),
  },

  defaultModel: {
    get: () => apiClient.get<DefaultModelConfig>('/models/default'),
    set: (data: DefaultModelConfig) => apiClient.put<DefaultModelConfig>('/models/default', data),
  },

  taskRouting: {
    get: () => apiClient.get<{ tasks: Record<string, { provider: string; model: string }> }>('/models/routing/tasks'),
    set: (tasks: Record<string, { provider: string; model: string }>) =>
      apiClient.put<{ tasks: Record<string, { provider: string; model: string }> }>('/models/routing/tasks', { tasks }),
  },

  availableModels: {
    list: () => apiClient.get<AvailableModel[]>('/models/available'),
  },

  presets: {
    list: () => apiClient.get<PresetInfo[]>('/models/presets'),
  },

  usage: {
    summary: (days = 30) =>
      apiClient.get<UsageSummary>('/models/usage/summary', { days }),
    providers: (days = 30) =>
      apiClient.get<ProviderUsageRow[]>('/models/usage/providers', { days }),
    requests: (days = 7, limit = 100) =>
      apiClient.get<RequestLogRow[]>('/models/usage/requests', { days, limit }),
    trends: (days = 30) =>
      apiClient.get<UsageTrendRow[]>('/models/usage/trends', { days }),
  },

  pricing: {
    list: () => apiClient.get<PricingEntry[]>('/models/pricing'),
    update: (model: string, data: PricingEntry) =>
      apiClient.put<PricingEntry>(`/models/pricing/${encodeURIComponent(model)}`, data),
  },

  health: {
    all: () => apiClient.get<ProviderHealthEntry[]>('/models/health'),
    checkAll: () => apiClient.post<TestResult[]>('/models/health/check-all'),
  },

  modelConfig: {
    export: (includeSecrets = false) =>
      apiClient.get<Record<string, unknown>>('/models/config/export', { include_secrets: includeSecrets }),
    import: (config: Record<string, unknown>, merge = true) =>
      apiClient.post<Record<string, unknown>>('/models/config/import', { config, merge }),
    backup: () => apiClient.post<{ backup_id: string }>('/models/config/backup'),
    backups: () => apiClient.get<string[]>('/models/config/backups'),
    restore: (backupId: string) =>
      apiClient.post<Record<string, unknown>>(`/models/config/restore/${encodeURIComponent(backupId)}`),
  },

  tools: {
    list: async () => {
      const res = await apiClient.get<{ tools: Array<{ name: string; description: string; category: string; version: string; timeout_sec: number; max_retries: number; requires_gpu: boolean }>; total: number; categories: Record<string, number> }>('/tools');
      return res.tools.map((t): Tool => ({
        id: t.name,
        name: t.name,
        description: t.description,
        category: t.category as Tool['category'],
        version: t.version,
        timeout_sec: t.timeout_sec,
        max_retries: t.max_retries,
        requires_gpu: t.requires_gpu,
        enabled: true,
        config: {},
      }));
    },
    get: (id: string) => apiClient.get<Tool>(`/tools/${id}`),
    toggle: (id: string, enabled: boolean) => apiClient.patch<Tool>(`/tools/${id}`, { enabled }),
    updateConfig: (id: string, config: ToolConfig['config']) =>
      apiClient.put<Tool>(`/tools/${id}/config`, config),
  },

  rules: {
    list: () => apiClient.get<RuleSetInfo[]>('/rules'),
    get: (id: string) => apiClient.get<RuleSetDetail>(`/rules/${id}`),
    create: (data: RuleSetCreateData) => apiClient.post<RuleSetInfo>('/rules', data),
    update: (id: string, data: RuleSetUpdateData) => apiClient.put<RuleSetDetail>(`/rules/${id}`, data),
    evaluate: (id: string, data: Record<string, unknown>) =>
      apiClient.post<RuleEvaluateResponse>(`/rules/${id}/evaluate`, { data }),
    reload: () => apiClient.post<{ message: string }>('/rules/reload'),
  },

  users: {
    list: (params: { page?: number; page_size?: number; search?: string; role?: string; status?: string; department?: string }) =>
      apiClient.get<PaginatedResponse<User>>('/users', params as Record<string, string | number | boolean | undefined>),
    get: (id: string) => apiClient.get<User>(`/users/${id}`),
    create: (data: UserFormData & { password: string }) => apiClient.post<User>('/users', data),
    update: (id: string, data: Partial<UserFormData>) => apiClient.put<User>(`/users/${id}`, data),
  },

  tasks: {
    list: (params: {
      page?: number;
      page_size?: number;
      status?: string;
      task_type?: string;
      priority?: string;
      user_id?: string;
      flow_id?: string;
      search?: string;
    }) =>
      apiClient.get<PaginatedResponse<Task>>(
        '/admin/tasks',
        params as Record<string, string | number | boolean | undefined>,
      ),
    get: (id: string) => apiClient.get<Task>(`/admin/tasks/${id}`),
    cancel: (id: string) =>
      apiClient.post<{
        task_id: string;
        ok: boolean;
        previous_status: string;
        new_status?: string;
        message: string;
      }>(`/admin/tasks/${id}/cancel`),
    kill: (id: string) =>
      apiClient.post<{
        task_id: string;
        ok: boolean;
        previous_status: string;
        new_status?: string;
        message: string;
      }>(`/admin/tasks/${id}/kill`),
    retry: (id: string) =>
      apiClient.post<{
        original_task_id: string;
        new_task: Task;
        message: string;
      }>(`/admin/tasks/${id}/retry`),
  },

  apiKeys: {
    list: () => apiClient.get<ApiKeyInfo[]>('/admin/api-keys'),
    create: (name: string) => apiClient.post<ApiKeyInfo>('/admin/api-keys', { name }),
    delete: (id: string) => apiClient.delete(`/admin/api-keys/${id}`),
  },

  imageGen: {
    presets: {
      list: () => apiClient.get<ImageGenPreset[]>('/models/image-gen/presets'),
      create: (data: ImageGenPreset) =>
        apiClient.post<ImageGenPreset>('/models/image-gen/presets', data),
      update: (id: string, data: ImageGenPreset) =>
        apiClient.put<ImageGenPreset>(`/models/image-gen/presets/${encodeURIComponent(id)}`, data),
      delete: (id: string) =>
        apiClient.delete(`/models/image-gen/presets/${encodeURIComponent(id)}`),
    },
    default: {
      get: () => apiClient.get<ImageGenDefault>('/models/image-gen/default'),
      set: (presetId: string) =>
        apiClient.put<ImageGenDefault>('/models/image-gen/default', { preset_id: presetId }),
    },
    backends: () => apiClient.get<ImageGenBackend[]>('/models/image-gen/backends'),
    models: (backend: string) =>
      apiClient.get<string[]>('/models/image-gen/models', { backend }),
    credentials: {
      list: () => apiClient.get<ImageGenCredentialStatus[]>('/models/image-gen/credentials'),
      set: (backend: string, data: ImageGenCredentialUpdate) =>
        apiClient.put<ImageGenCredentialStatus>(
          `/models/image-gen/credentials/${encodeURIComponent(backend)}`,
          data,
        ),
    },
    local: {
      get: () => apiClient.get<ImageGenLocalConfig>('/models/image-gen/local'),
      set: (data: ImageGenLocalConfig) =>
        apiClient.put<ImageGenLocalConfig>('/models/image-gen/local', data),
    },
    providers: {
      list: () => apiClient.get<ImageGenCustomProvider[]>('/models/image-gen/providers'),
      create: (data: ImageGenCustomProviderUpdate) =>
        apiClient.post<ImageGenCustomProvider>('/models/image-gen/providers', data),
      update: (name: string, data: ImageGenCustomProviderUpdate) =>
        apiClient.put<ImageGenCustomProvider>(
          `/models/image-gen/providers/${encodeURIComponent(name)}`,
          data,
        ),
      delete: (name: string) =>
        apiClient.delete(`/models/image-gen/providers/${encodeURIComponent(name)}`),
    },
    test: (data: ImageGenTestRequest) =>
      apiClient.post<ImageGenTestResult>('/models/image-gen/test', data),
  },
};
