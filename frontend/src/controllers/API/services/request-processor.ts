import {
  useQuery,
  useMutation,
  useQueryClient,
  UseQueryOptions,
  UseMutationOptions,
  QueryKey,
  UseQueryResult,
  UseMutationResult,
} from '@tanstack/react-query';
import { apiClient, type ApiError } from '@/api/client';
import { CACHE_TIME } from '../helpers/constants';

export interface QueryOptions<TData, TError = ApiError>
  extends Omit<UseQueryOptions<TData, TError>, 'queryKey' | 'queryFn'> {
  queryKey: QueryKey;
  url: string;
  params?: Record<string, string | number | boolean | undefined>;
}

export interface MutationOptions<TData, TVariables, TError = ApiError>
  extends Omit<UseMutationOptions<TData, TError, TVariables>, 'mutationFn'> {
  url: string | ((variables: TVariables) => string);
  method?: 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  invalidateKeys?: QueryKey[];
}

interface RequestProcessorReturn {
  query: <TData, TError = ApiError>(
    options: QueryOptions<TData, TError>
  ) => UseQueryResult<TData, TError>;

  mutate: <TData, TVariables, TError = ApiError>(
    options: MutationOptions<TData, TVariables, TError>
  ) => UseMutationResult<TData, TError, TVariables>;
}

export const useRequestProcessor = (): RequestProcessorReturn => {
  const queryClient = useQueryClient();

  const query = <TData, TError = ApiError>(
    options: QueryOptions<TData, TError>
  ): UseQueryResult<TData, TError> => {
    const { queryKey, url, params, ...queryOptions } = options;

    return useQuery<TData, TError>({
      queryKey,
      queryFn: () => apiClient.get<TData>(url, params),
      staleTime: CACHE_TIME.STALE_TIME_MEDIUM,
      gcTime: CACHE_TIME.GC_TIME,
      ...queryOptions,
    });
  };

  const mutate = <TData, TVariables, TError = ApiError>(
    options: MutationOptions<TData, TVariables, TError>
  ): UseMutationResult<TData, TError, TVariables> => {
    const { url, method = 'POST', invalidateKeys, ...mutationOptions } = options;

    return useMutation<TData, TError, TVariables>({
      mutationFn: async (variables: TVariables) => {
        const resolvedUrl = typeof url === 'function' ? url(variables) : url;

        switch (method) {
          case 'POST':
            return apiClient.post<TData>(resolvedUrl, variables);
          case 'PUT':
            return apiClient.put<TData>(resolvedUrl, variables);
          case 'PATCH':
            return apiClient.patch<TData>(resolvedUrl, variables);
          case 'DELETE':
            return apiClient.delete<TData>(resolvedUrl);
          default:
            throw new Error(`Unsupported method: ${method}`);
        }
      },
      onSuccess: async (data, variables, onMutateResult, context) => {
        if (invalidateKeys && invalidateKeys.length > 0) {
          await Promise.all(
            invalidateKeys.map((key) => queryClient.invalidateQueries({ queryKey: key }))
          );
        }
        mutationOptions.onSuccess?.(data, variables, onMutateResult, context);
      },
      ...mutationOptions,
    });
  };

  return { query, mutate };
};

export const createQueryFn = <TData>(url: string, params?: Record<string, string | number | boolean | undefined>) => {
  return (): Promise<TData> => apiClient.get<TData>(url, params);
};

export const createMutationFn = <TData, TVariables>(
  url: string | ((variables: TVariables) => string),
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE' = 'POST'
) => {
  return async (variables: TVariables): Promise<TData> => {
    const resolvedUrl = typeof url === 'function' ? url(variables) : url;

    switch (method) {
      case 'POST':
        return apiClient.post<TData>(resolvedUrl, variables);
      case 'PUT':
        return apiClient.put<TData>(resolvedUrl, variables);
      case 'PATCH':
        return apiClient.patch<TData>(resolvedUrl, variables);
      case 'DELETE':
        return apiClient.delete<TData>(resolvedUrl);
    }
  };
};

export type { ApiError };
