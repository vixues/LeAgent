import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import { apiClient, type ApiError } from '@/api/client';
import { CACHE_TIME } from '@/controllers/API/helpers/constants';

// ---- Types ----

export type ChannelType = 'dingtalk' | 'feishu' | 'wechat_work' | 'weixin' | 'web' | 'api' | 'console';
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

/** Weixin iLink QR login */
export interface WeixinLoginStartResponse {
  qrcode: string;
  qr_url: string;
  qr_image_data_url: string;
  base_url: string;
  status: string;
}

export interface WeixinLoginStatusResponse {
  status: string;
  qrcode: string;
  connected: boolean;
  account_id: string;
  base_url: string;
  running: boolean;
  message: string;
}

export interface WeixinRuntimeResponse {
  enabled: boolean;
  configured: boolean;
  running: boolean;
  account_id: string;
  session_expired: boolean;
}

const QK = {
  list: (filters?: ChannelFilters) => ['channels', 'list', filters] as const,
  detail: (id: string) => ['channels', 'detail', id] as const,
  weixinRuntime: ['channels', 'weixin', 'runtime'] as const,
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

export function useWeixinRuntime(
  options?: Omit<UseQueryOptions<WeixinRuntimeResponse, ApiError>, 'queryKey' | 'queryFn'>
) {
  return useQuery<WeixinRuntimeResponse, ApiError>({
    queryKey: QK.weixinRuntime,
    queryFn: () => apiClient.get<WeixinRuntimeResponse>('/channels/weixin/runtime'),
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    // Only poll while the long-poller is live — stopped state must not keep
    // hitting the API / writing access logs every 10s.
    refetchInterval: (query) => (query.state.data?.running ? 10_000 : false),
    refetchIntervalInBackground: false,
    ...options,
  });
}

export function useWeixinLoginStart() {
  return useMutation<WeixinLoginStartResponse, ApiError, { base_url?: string } | void>({
    mutationFn: (input) =>
      apiClient.post<WeixinLoginStartResponse>('/channels/weixin/login/start', input ?? {}),
  });
}

export function useWeixinLoginStatus() {
  const queryClient = useQueryClient();
  return useMutation<
    WeixinLoginStatusResponse,
    ApiError,
    { qrcode: string; base_url?: string }
  >({
    mutationFn: ({ qrcode, base_url }) =>
      apiClient.get<WeixinLoginStatusResponse>('/channels/weixin/login/status', {
        qrcode,
        base_url,
      }),
    onSuccess: (data) => {
      if (data.connected) {
        queryClient.invalidateQueries({ queryKey: QK.weixinRuntime });
        queryClient.invalidateQueries({ queryKey: ['channels', 'list'] });
      }
    },
  });
}

export function useWeixinStart() {
  const queryClient = useQueryClient();
  return useMutation<WeixinRuntimeResponse, ApiError, void>({
    mutationFn: () => apiClient.post<WeixinRuntimeResponse>('/channels/weixin/start'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QK.weixinRuntime });
    },
  });
}

export function useWeixinStop() {
  const queryClient = useQueryClient();
  return useMutation<WeixinRuntimeResponse, ApiError, void>({
    mutationFn: () => apiClient.post<WeixinRuntimeResponse>('/channels/weixin/stop'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QK.weixinRuntime });
    },
  });
}
