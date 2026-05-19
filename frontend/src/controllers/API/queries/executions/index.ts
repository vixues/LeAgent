import { useQuery, useMutation, useQueryClient, UseQueryOptions } from '@tanstack/react-query';
import { apiClient, ApiError } from '@/api/client';
import { URL_KEYS, QUERY_KEYS, CACHE_TIME } from '../../helpers/constants';

// ---- Types ----

export interface WorkflowExecutionSummary {
  id: string;
  flow_id?: string;
  status: 'pending' | 'running' | 'paused' | 'waiting_human' | 'completed' | 'failed' | 'cancelled' | 'timeout';
  trigger_type: string;
  node_count: number;
  duration_ms: number;
  error?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
}

export interface NodeExecutionResult {
  node_id: string;
  status: string;
  output?: unknown;
  error?: string;
  duration_ms: number;
  next_node?: string;
  metadata?: Record<string, unknown>;
}

export interface WorkflowExecutionDetail extends WorkflowExecutionSummary {
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  execution_history: NodeExecutionResult[];
  current_node?: string;
}

export interface WorkflowExecutionListResponse {
  executions: WorkflowExecutionSummary[];
  total: number;
}

// ---- Queries ----

export const useFlowExecutions = (
  flowId: string,
  params?: { limit?: number; offset?: number },
  options?: Omit<UseQueryOptions<WorkflowExecutionListResponse, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<WorkflowExecutionListResponse, ApiError>({
    queryKey: [...QUERY_KEYS.EXECUTIONS(flowId), params],
    queryFn: async () => {
      return apiClient.get<WorkflowExecutionListResponse>(
        URL_KEYS.FLOW_EXECUTIONS(flowId),
        params as Record<string, string | number | boolean | undefined>,
      );
    },
    enabled: !!flowId,
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    ...options,
  });
};

export const useExecution = (
  executionId: string,
  options?: Omit<UseQueryOptions<WorkflowExecutionDetail, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<WorkflowExecutionDetail, ApiError>({
    queryKey: QUERY_KEYS.EXECUTION(executionId),
    queryFn: async () => {
      return apiClient.get<WorkflowExecutionDetail>(URL_KEYS.FLOW_EXECUTION_BY_ID(executionId));
    },
    enabled: !!executionId,
    staleTime: 5000,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'running' || status === 'pending') {
        return 3000;
      }
      return false;
    },
    ...options,
  });
};

// ---- Mutations ----

export const useCancelExecution = () => {
  const queryClient = useQueryClient();
  return useMutation<{ execution_id: string; status: string }, ApiError, string>({
    mutationFn: async (executionId) => {
      return apiClient.post<{ execution_id: string; status: string }>(URL_KEYS.FLOW_EXECUTION_CANCEL(executionId));
    },
    onSuccess: (_, executionId) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.EXECUTION(executionId) });
    },
  });
};

export const usePauseExecution = () => {
  const queryClient = useQueryClient();
  return useMutation<{ execution_id: string; status: string }, ApiError, string>({
    mutationFn: async (executionId) => {
      return apiClient.post<{ execution_id: string; status: string }>(URL_KEYS.FLOW_EXECUTION_PAUSE(executionId));
    },
    onSuccess: (_, executionId) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.EXECUTION(executionId) });
    },
  });
};

export const useResumeExecution = () => {
  const queryClient = useQueryClient();
  return useMutation<
    { execution_id: string; status: string },
    ApiError,
    { executionId: string; flowId: string; resumeData?: Record<string, unknown> }
  >({
    mutationFn: async ({ executionId, flowId, resumeData }) => {
      return apiClient.post<{ execution_id: string; status: string }>(
        URL_KEYS.FLOW_EXECUTION_RESUME(executionId),
        resumeData,
        { params: { flow_id: flowId } },
      );
    },
    onSuccess: (_, { executionId }) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.EXECUTION(executionId) });
    },
  });
};

export interface RunFlowInput {
  flowId: string;
  inputData?: Record<string, unknown>;
  priority?: number;
  triggerType?: string;
  sessionId?: string | null;
  extraData?: Record<string, unknown>;
}

export interface RunFlowResponse {
  execution_id: string;
  prompt_id: string;
  flow_id: string;
  status: string;
  queue_position?: number | null;
  message?: string;
}

export const useRunFlow = () => {
  const queryClient = useQueryClient();
  return useMutation<RunFlowResponse, ApiError, RunFlowInput>({
    mutationFn: async ({
      flowId,
      inputData,
      priority,
      triggerType,
      sessionId,
      extraData,
    }) => {
      return apiClient.post<RunFlowResponse>(URL_KEYS.FLOW_RUN(flowId), {
        input_data: inputData ?? {},
        priority: priority ?? 5,
        trigger_type: triggerType ?? 'manual',
        session_id: sessionId ?? null,
        extra_data: extraData ?? {},
      });
    },
    onSuccess: (data) => {
      if (data.flow_id) {
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.EXECUTIONS(data.flow_id) });
      }
    },
  });
};
