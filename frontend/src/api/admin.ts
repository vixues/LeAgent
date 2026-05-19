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
  },

  defaultModel: {
    get: () => apiClient.get<DefaultModelConfig>('/models/default'),
    set: (data: DefaultModelConfig) => apiClient.put<DefaultModelConfig>('/models/default', data),
  },

  presets: {
    list: () => apiClient.get<PresetInfo[]>('/models/presets'),
  },

  usage: {
    summary: (days = 30) =>
      apiClient.get<UsageSummary>('/models/usage/summary', { days }),
  },

  health: {
    all: () => apiClient.get<ProviderHealthEntry[]>('/models/health'),
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
};
