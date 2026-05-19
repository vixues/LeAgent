import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import { apiClient, type ApiError } from '@/api/client';
import { CACHE_TIME } from '@/controllers/API/helpers/constants';

// ---- Types ----

/** Event names accepted by the API (see backend `WebhookEvent`). */
export const WEBHOOK_EVENT_OPTIONS = [
  'task.created',
  'task.completed',
  'task.failed',
  'flow.run.started',
  'flow.run.completed',
  'flow.run.failed',
  'message.received',
  'file.uploaded',
  'file.deleted',
  'user.login',
  'user.logout',
  'file.processed',
  'user.created',
  'user.updated',
] as const;

export type WebhookEventName = (typeof WEBHOOK_EVENT_OPTIONS)[number];

export interface WebhookInfo {
  id: string;
  name: string;
  url: string;
  events: string[];
  status: string;
  enabled: boolean;
  description?: string;
  delivery_count?: number;
  failure_count?: number;
  last_delivery_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface WebhookDetail extends WebhookInfo {
  secret?: string;
  headers?: Record<string, string>;
  retry_count: number;
  timeout_seconds: number;
  last_error?: string;
}

export interface WebhookListResponse {
  webhooks: WebhookInfo[];
  total: number;
}

export interface WebhookFilters {
  status?: string;
  event?: string;
}

export interface CreateWebhookInput {
  name: string;
  url: string;
  events: string[];
  description?: string;
  secret?: string;
  headers?: Record<string, string>;
  retry_count?: number;
  timeout_seconds?: number;
  enabled?: boolean;
}

export interface UpdateWebhookInput {
  id: string;
  name?: string;
  url?: string;
  events?: string[];
  description?: string;
  secret?: string;
  headers?: Record<string, string>;
  retry_count?: number;
  timeout_seconds?: number;
  enabled?: boolean;
}

export interface WebhookTestResponse {
  webhook_id: string;
  success: boolean;
  status_code?: number | null;
  response_time_ms: number;
  error?: string | null;
}

export interface WebhookDeliveryLog {
  id: string;
  webhook_id: string;
  event: string;
  payload: Record<string, unknown>;
  status_code: number | null;
  success: boolean;
  response_time_ms: number;
  error?: string | null;
  created_at: string;
}

export interface WebhookToggleResponse {
  webhook_id: string;
  status: string;
  message?: string;
}

const QK = {
  list: (filters?: WebhookFilters) => ['webhooks', 'list', filters] as const,
  detail: (id: string) => ['webhooks', 'detail', id] as const,
  deliveries: (id: string) => ['webhooks', id, 'deliveries'] as const,
};

// ---- Queries ----

export function useWebhooksList(
  filters?: WebhookFilters,
  options?: Omit<UseQueryOptions<WebhookListResponse, ApiError>, 'queryKey' | 'queryFn'>
) {
  return useQuery<WebhookListResponse, ApiError>({
    queryKey: QK.list(filters),
    queryFn: () =>
      apiClient.get<WebhookListResponse>('/webhooks', filters as Record<string, string | undefined>),
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    ...options,
  });
}

export function useWebhookDetail(
  id: string,
  options?: Omit<UseQueryOptions<WebhookDetail, ApiError>, 'queryKey' | 'queryFn'>
) {
  return useQuery<WebhookDetail, ApiError>({
    queryKey: QK.detail(id),
    queryFn: () => apiClient.get<WebhookDetail>(`/webhooks/${id}`),
    enabled: !!id,
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    ...options,
  });
}

export function useWebhookDeliveries(
  id: string,
  options?: Omit<UseQueryOptions<WebhookDeliveryLog[], ApiError>, 'queryKey' | 'queryFn'>
) {
  const { enabled: enabledOption, ...rest } = options ?? {};
  return useQuery<WebhookDeliveryLog[], ApiError>({
    queryKey: QK.deliveries(id),
    queryFn: () => apiClient.get<WebhookDeliveryLog[]>(`/webhooks/${id}/deliveries`),
    enabled: !!id && (enabledOption ?? true),
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    ...rest,
  });
}

// ---- Mutations ----

export function useCreateWebhook() {
  const queryClient = useQueryClient();
  return useMutation<WebhookDetail, ApiError, CreateWebhookInput>({
    mutationFn: (input) => apiClient.post<WebhookDetail>('/webhooks', input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['webhooks', 'list'] });
    },
  });
}

export function useUpdateWebhook() {
  const queryClient = useQueryClient();
  return useMutation<WebhookDetail, ApiError, UpdateWebhookInput>({
    mutationFn: ({ id, ...data }) => apiClient.put<WebhookDetail>(`/webhooks/${id}`, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['webhooks', 'list'] });
      queryClient.setQueryData(QK.detail(data.id), data);
    },
  });
}

export function useDeleteWebhook() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => apiClient.delete(`/webhooks/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['webhooks', 'list'] });
    },
  });
}

export function useTestWebhook() {
  const queryClient = useQueryClient();
  return useMutation<WebhookTestResponse, ApiError, string>({
    mutationFn: (id) => apiClient.post<WebhookTestResponse>(`/webhooks/${id}/test`),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: QK.deliveries(id) });
      queryClient.invalidateQueries({ queryKey: ['webhooks', 'list'] });
    },
  });
}

export function useEnableWebhook() {
  const queryClient = useQueryClient();
  return useMutation<WebhookToggleResponse, ApiError, string>({
    mutationFn: (id) => apiClient.post<WebhookToggleResponse>(`/webhooks/${id}/enable`),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['webhooks', 'list'] });
      queryClient.invalidateQueries({ queryKey: QK.detail(id) });
    },
  });
}

export function useDisableWebhook() {
  const queryClient = useQueryClient();
  return useMutation<WebhookToggleResponse, ApiError, string>({
    mutationFn: (id) => apiClient.post<WebhookToggleResponse>(`/webhooks/${id}/disable`),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['webhooks', 'list'] });
      queryClient.invalidateQueries({ queryKey: QK.detail(id) });
    },
  });
}
