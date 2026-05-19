import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import { apiClient, type ApiError } from '@/api/client';
import { CACHE_TIME } from '@/controllers/API/helpers/constants';

// ---- Types ----

export type ChannelType = 'dingtalk' | 'feishu' | 'wechat_work' | 'web' | 'api' | 'console';
export type ChannelStatus = 'active' | 'inactive' | 'error';

export interface ChannelConfig {
  id: string;
  name: string;
  channel_type: ChannelType;
  status: ChannelStatus;
  enabled: boolean;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ChannelListResponse {
  channels: ChannelConfig[];
  total: number;
}

export interface ChannelFilters {
  status?: string;
  channel_type?: string;
}

export interface CreateChannelInput {
  name: string;
  channel_type: ChannelType;
  enabled?: boolean;
  config?: Record<string, unknown>;
}

export interface UpdateChannelInput {
  id: string;
  name?: string;
  enabled?: boolean;
  config?: Record<string, unknown>;
}

/** Response from POST /channels/{id}/test */
export interface ChannelTestResponse {
  channel_id: string;
  channel_type: ChannelType;
  success: boolean;
  latency_ms: number;
  error?: string | null;
}

/** Response from POST /channels/{id}/activate | deactivate */
export interface ChannelStateResponse {
  channel_id: string;
  status: string;
  message?: string;
}

const QK = {
  list: (filters?: ChannelFilters) => ['channels', 'list', filters] as const,
  detail: (id: string) => ['channels', 'detail', id] as const,
};

// ---- Queries ----

export function useChannelsList(
  filters?: ChannelFilters,
  options?: Omit<UseQueryOptions<ChannelListResponse, ApiError>, 'queryKey' | 'queryFn'>
) {
  return useQuery<ChannelListResponse, ApiError>({
    queryKey: QK.list(filters),
    queryFn: () =>
      apiClient.get<ChannelListResponse>('/channels', filters as Record<string, string | undefined>),
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    ...options,
  });
}

export function useChannelDetail(
  id: string,
  options?: Omit<UseQueryOptions<ChannelConfig, ApiError>, 'queryKey' | 'queryFn'>
) {
  return useQuery<ChannelConfig, ApiError>({
    queryKey: QK.detail(id),
    queryFn: () => apiClient.get<ChannelConfig>(`/channels/${id}`),
    enabled: !!id,
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    ...options,
  });
}

// ---- Mutations ----

export function useCreateChannel() {
  const queryClient = useQueryClient();
  return useMutation<ChannelConfig, ApiError, CreateChannelInput>({
    mutationFn: (input) => apiClient.post<ChannelConfig>('/channels', input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['channels', 'list'] });
    },
  });
}

export function useUpdateChannel() {
  const queryClient = useQueryClient();
  return useMutation<ChannelConfig, ApiError, UpdateChannelInput>({
    mutationFn: ({ id, ...data }) => apiClient.put<ChannelConfig>(`/channels/${id}`, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['channels', 'list'] });
      queryClient.setQueryData(QK.detail(data.id), data);
    },
  });
}

export function useDeleteChannel() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => apiClient.delete(`/channels/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['channels', 'list'] });
    },
  });
}

export function useTestChannel() {
  const queryClient = useQueryClient();
  return useMutation<ChannelTestResponse, ApiError, string>({
    mutationFn: (id) => apiClient.post<ChannelTestResponse>(`/channels/${id}/test`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['channels', 'list'] });
    },
  });
}

export function useActivateChannel() {
  const queryClient = useQueryClient();
  return useMutation<ChannelStateResponse, ApiError, string>({
    mutationFn: (id) => apiClient.post<ChannelStateResponse>(`/channels/${id}/activate`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['channels', 'list'] });
      queryClient.invalidateQueries({ queryKey: ['channels', 'detail'] });
    },
  });
}

export function useDeactivateChannel() {
  const queryClient = useQueryClient();
  return useMutation<ChannelStateResponse, ApiError, string>({
    mutationFn: (id) => apiClient.post<ChannelStateResponse>(`/channels/${id}/deactivate`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['channels', 'list'] });
      queryClient.invalidateQueries({ queryKey: ['channels', 'detail'] });
    },
  });
}
