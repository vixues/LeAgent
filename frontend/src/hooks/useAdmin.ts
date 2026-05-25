import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminApi } from '@/api/admin';
import type {
  ModelProviderFormData,
  DefaultModelConfig,
  ToolConfig,
  RuleSetCreateData,
  RuleSetUpdateData,
} from '@/types/admin';

const QUERY_KEYS = {
  providers: ['models', 'providers'] as const,
  defaultModel: ['models', 'default'] as const,
  presets: ['models', 'presets'] as const,
  usage: ['models', 'usage'] as const,
  health: ['models', 'health'] as const,
  pricing: ['models', 'pricing'] as const,
  tools: ['admin', 'tools'] as const,
  rules: ['admin', 'rules'] as const,
  tasks: ['admin', 'tasks'] as const,
};

export function useProviders() {
  return useQuery({
    queryKey: QUERY_KEYS.providers,
    queryFn: adminApi.providers.list,
  });
}

export function useProvider(name: string) {
  return useQuery({
    queryKey: [...QUERY_KEYS.providers, name],
    queryFn: () => adminApi.providers.get(name),
    enabled: !!name,
  });
}

export function useCreateProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ModelProviderFormData) => adminApi.providers.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.providers });
    },
  });
}

export function useUpdateProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, data }: { name: string; data: Partial<ModelProviderFormData> }) =>
      adminApi.providers.update(name, data),
    onSuccess: (_, { name }) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.providers });
      queryClient.invalidateQueries({ queryKey: [...QUERY_KEYS.providers, name] });
    },
  });
}

export function useDeleteProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => adminApi.providers.delete(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.providers });
    },
  });
}

export function useTestProvider() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => adminApi.providers.test(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.providers });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.health });
    },
  });
}

export function useDiscoverProviderModels() {
  return useMutation({
    mutationFn: (name: string) => adminApi.providers.discover(name),
  });
}

export function useSpeedTestProvider() {
  return useMutation({
    mutationFn: ({ name, candidates }: { name: string; candidates: string[] }) =>
      adminApi.providers.speedTest(name, candidates),
  });
}

export function useCheckAllProvidersHealth() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.health.checkAll,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.providers });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.health });
    },
  });
}

export function useDefaultModel() {
  return useQuery({
    queryKey: QUERY_KEYS.defaultModel,
    queryFn: adminApi.defaultModel.get,
  });
}

export function useSetDefaultModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: DefaultModelConfig) => adminApi.defaultModel.set(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.defaultModel });
    },
  });
}

export function usePresets() {
  return useQuery({
    queryKey: QUERY_KEYS.presets,
    queryFn: adminApi.presets.list,
    staleTime: 5 * 60 * 1000,
  });
}

export function useModelUsageSummary(days = 30) {
  return useQuery({
    queryKey: [...QUERY_KEYS.usage, days],
    queryFn: () => adminApi.usage.summary(days),
    staleTime: 60 * 1000,
  });
}

export function useProviderUsage(days = 30) {
  return useQuery({
    queryKey: [...QUERY_KEYS.usage, 'providers', days],
    queryFn: () => adminApi.usage.providers(days),
    staleTime: 60 * 1000,
  });
}

export function useRequestLogs(days = 7, limit = 100) {
  return useQuery({
    queryKey: [...QUERY_KEYS.usage, 'requests', days, limit],
    queryFn: () => adminApi.usage.requests(days, limit),
    staleTime: 30 * 1000,
  });
}

export function useUsageTrends(days = 30) {
  return useQuery({
    queryKey: [...QUERY_KEYS.usage, 'trends', days],
    queryFn: () => adminApi.usage.trends(days),
    staleTime: 60 * 1000,
  });
}

export function usePricing() {
  return useQuery({
    queryKey: QUERY_KEYS.pricing,
    queryFn: adminApi.pricing.list,
    staleTime: 5 * 60 * 1000,
  });
}

export function useAllProvidersHealth() {
  return useQuery({
    queryKey: QUERY_KEYS.health,
    queryFn: adminApi.health.all,
    staleTime: 30 * 1000,
  });
}

export function useTools() {
  return useQuery({
    queryKey: QUERY_KEYS.tools,
    queryFn: adminApi.tools.list,
  });
}

export function useToggleTool() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      adminApi.tools.toggle(id, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.tools });
    },
  });
}

export function useUpdateToolConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, config }: { id: string; config: ToolConfig['config'] }) =>
      adminApi.tools.updateConfig(id, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.tools });
    },
  });
}

export function useRules() {
  return useQuery({
    queryKey: QUERY_KEYS.rules,
    queryFn: adminApi.rules.list,
  });
}

export function useRule(id: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: [...QUERY_KEYS.rules, id],
    queryFn: () => adminApi.rules.get(id),
    enabled: !!id && (options?.enabled ?? true),
  });
}

export function useCreateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: RuleSetCreateData) => adminApi.rules.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.rules });
    },
  });
}

export function useUpdateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: RuleSetUpdateData }) =>
      adminApi.rules.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.rules });
      queryClient.invalidateQueries({ queryKey: [...QUERY_KEYS.rules, id] });
    },
  });
}

export function useEvaluateRule() {
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      adminApi.rules.evaluate(id, data),
  });
}

export function useTestRule() {
  return useEvaluateRule();
}

export function useReloadRules() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => adminApi.rules.reload(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.rules });
    },
  });
}

export function useTasks(params: {
  page?: number;
  pageSize?: number;
  status?: string;
  task_type?: string;
  priority?: string;
  user_id?: string;
  flow_id?: string;
  search?: string;
}) {
  return useQuery({
    queryKey: [...QUERY_KEYS.tasks, params],
    queryFn: () =>
      adminApi.tasks.list({
        page: params.page,
        page_size: params.pageSize,
        status: params.status,
        task_type: params.task_type,
        priority: params.priority,
        user_id: params.user_id,
        flow_id: params.flow_id,
        search: params.search,
      }),
    refetchInterval: 5000,
  });
}

export function useTask(id: string) {
  return useQuery({
    queryKey: [...QUERY_KEYS.tasks, id],
    queryFn: () => adminApi.tasks.get(id),
    enabled: !!id,
    refetchInterval: 3000,
  });
}

export function useCancelTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => adminApi.tasks.cancel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.tasks });
    },
  });
}

export function useKillTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => adminApi.tasks.kill(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.tasks });
    },
  });
}

export function useRetryTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => adminApi.tasks.retry(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.tasks });
    },
  });
}
