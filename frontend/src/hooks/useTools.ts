import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/api/client';
import type { Tool, ToolDetail, ToolCategory } from '@/types/admin';
import { QUERY_KEYS, CACHE_TIME } from '@/controllers/API/helpers/constants';

interface ToolInfoResponse {
  name: string;
  description: string;
  category: string;
  version: string;
  timeout_sec: number;
  max_retries: number;
  requires_gpu: boolean;
}

interface ToolsListResponse {
  tools: ToolInfoResponse[];
  total: number;
  categories: Record<string, number>;
}

interface ToolDetailResponse extends ToolInfoResponse {
  parameters: Record<string, unknown>;
}

function mapToolInfo(t: ToolInfoResponse): Tool {
  return {
    id: t.name,
    name: t.name,
    description: t.description,
    category: t.category as ToolCategory,
    version: t.version,
    timeout_sec: t.timeout_sec,
    max_retries: t.max_retries,
    requires_gpu: t.requires_gpu,
    enabled: true,
    config: {},
  };
}

export function useToolsList() {
  return useQuery({
    queryKey: QUERY_KEYS.TOOLS,
    queryFn: async () => {
      const res = await apiClient.get<ToolsListResponse>('/tools');
      return {
        tools: res.tools.map(mapToolInfo),
        total: res.total,
        categories: res.categories,
      };
    },
    staleTime: CACHE_TIME.STALE_TIME_LONG,
    retry: 2,
  });
}

export function useToolDetail(toolName: string | null) {
  return useQuery({
    queryKey: QUERY_KEYS.TOOL(toolName ?? ''),
    queryFn: async () => {
      const res = await apiClient.get<ToolDetailResponse>(`/tools/${toolName}`);
      return {
        ...mapToolInfo(res),
        parameters: res.parameters,
      } as ToolDetail;
    },
    enabled: !!toolName,
    staleTime: CACHE_TIME.STALE_TIME_LONG,
  });
}

export function useToolSchema(toolName: string | null) {
  return useQuery({
    queryKey: QUERY_KEYS.TOOL_SCHEMA(toolName ?? ''),
    queryFn: () => apiClient.get<Record<string, unknown>>(`/tools/${toolName}/schema`),
    enabled: !!toolName,
    staleTime: CACHE_TIME.STALE_TIME_VERY_LONG,
  });
}

export function useToggleTool() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, enabled }: { id: string; enabled: boolean }) => {
      return apiClient.patch(`/tools/${id}/toggle`, { enabled });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.TOOLS });
    },
  });
}

export function useUpdateToolConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, config }: { id: string; config: Record<string, unknown> }) => {
      return apiClient.patch(`/tools/${id}/config`, { config });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.TOOLS });
    },
  });
}
