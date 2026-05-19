import { useQuery, useMutation, useQueryClient, UseQueryOptions } from '@tanstack/react-query';
import { apiClient, ApiError } from '@/api/client';
import { URL_KEYS, QUERY_KEYS, CACHE_TIME } from '../../helpers/constants';
import type { FlowData, FlowValidationResult } from '@/types/flow';

export interface FlowListParams {
  page?: number;
  pageSize?: number;
  search?: string;
  tags?: string[];
  sortBy?: 'name' | 'createdAt' | 'updatedAt';
  sortOrder?: 'asc' | 'desc';
}

export interface FlowListResponse {
  data: FlowData[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

interface BackendPaginatedFlows {
  items: FlowData[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface CreateFlowInput {
  name: string;
  description?: string;
  nodes?: FlowData['nodes'];
  edges?: FlowData['edges'];
  tags?: string[];
}

export interface UpdateFlowInput {
  id: string;
  name?: string;
  description?: string;
  nodes?: FlowData['nodes'];
  edges?: FlowData['edges'];
  tags?: string[];
}

export interface DuplicateFlowInput {
  id: string;
  newName?: string;
}

export interface ImportFlowInput {
  file?: File;
  data?: Record<string, unknown>;
}

export const useGetFlows = (
  params?: FlowListParams,
  options?: Omit<UseQueryOptions<FlowListResponse, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<FlowListResponse, ApiError>({
    queryKey: [...QUERY_KEYS.FLOWS, params],
    queryFn: async () => {
      const res = await apiClient.get<BackendPaginatedFlows>(URL_KEYS.FLOWS, {
        page: params?.page,
        page_size: params?.pageSize,
        search: params?.search,
      } as Record<string, string | number | boolean | undefined>);
      return {
        data: res.items,
        total: res.total,
        page: res.page,
        pageSize: res.page_size,
        totalPages: Math.ceil(res.total / res.page_size),
      };
    },
    staleTime: CACHE_TIME.STALE_TIME_MEDIUM,
    ...options,
  });
};

export const useGetFlow = (
  flowId: string,
  options?: Omit<UseQueryOptions<FlowData, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<FlowData, ApiError>({
    queryKey: QUERY_KEYS.FLOW(flowId),
    queryFn: async () => {
      return apiClient.get<FlowData>(URL_KEYS.FLOW_BY_ID(flowId));
    },
    staleTime: CACHE_TIME.STALE_TIME_MEDIUM,
    enabled: !!flowId,
    ...options,
  });
};

export const usePostAddFlow = () => {
  const queryClient = useQueryClient();

  return useMutation<FlowData, ApiError, CreateFlowInput>({
    mutationFn: async (input) => {
      return apiClient.post<FlowData>(URL_KEYS.FLOWS, input);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.FLOWS });
    },
  });
};

export const usePatchUpdateFlow = () => {
  const queryClient = useQueryClient();

  return useMutation<FlowData, ApiError, UpdateFlowInput>({
    mutationFn: async ({ id, ...data }) => {
      return apiClient.patch<FlowData>(URL_KEYS.FLOW_BY_ID(id), data);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.FLOWS });
      queryClient.setQueryData(QUERY_KEYS.FLOW(data.id), data);
    },
  });
};

export const usePutUpdateFlow = () => {
  const queryClient = useQueryClient();

  return useMutation<FlowData, ApiError, UpdateFlowInput>({
    mutationFn: async ({ id, ...data }) => {
      return apiClient.put<FlowData>(URL_KEYS.FLOW_BY_ID(id), data);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.FLOWS });
      queryClient.setQueryData(QUERY_KEYS.FLOW(data.id), data);
    },
  });
};

export const useDeleteFlow = () => {
  const queryClient = useQueryClient();

  return useMutation<void, ApiError, string>({
    mutationFn: async (flowId) => {
      await apiClient.delete(URL_KEYS.FLOW_BY_ID(flowId));
    },
    onSuccess: (_, flowId) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.FLOWS });
      queryClient.removeQueries({ queryKey: QUERY_KEYS.FLOW(flowId) });
    },
  });
};

export const useDuplicateFlow = () => {
  const queryClient = useQueryClient();

  return useMutation<FlowData, ApiError, DuplicateFlowInput>({
    mutationFn: async ({ id, newName }) => {
      return apiClient.post<FlowData>(URL_KEYS.FLOW_DUPLICATE(id), { name: newName });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.FLOWS });
    },
  });
};

export const useValidateFlow = (
  flowId: string,
  options?: Omit<UseQueryOptions<FlowValidationResult, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<FlowValidationResult, ApiError>({
    queryKey: QUERY_KEYS.FLOW_VALIDATION(flowId),
    queryFn: async () => {
      return apiClient.get<FlowValidationResult>(URL_KEYS.FLOW_VALIDATE(flowId));
    },
    enabled: !!flowId,
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    ...options,
  });
};

export const useExportFlow = () => {
  return useMutation<Blob, ApiError, string>({
    mutationFn: async (flowId) => {
      return apiClient.get<Blob>(URL_KEYS.FLOW_EXPORT(flowId));
    },
  });
};

export const useImportFlow = () => {
  const queryClient = useQueryClient();

  return useMutation<FlowData, ApiError, ImportFlowInput>({
    mutationFn: async (input) => {
      if (input.file) {
        const formData = new FormData();
        formData.append('file', input.file);
        return apiClient.upload<FlowData>(URL_KEYS.FLOW_IMPORT, formData);
      }
      return apiClient.post<FlowData>(URL_KEYS.FLOW_IMPORT, input.data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.FLOWS });
    },
  });
};
