import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '@/api/client';
import type {
  AgentRunRequest,
  AgentRunResponse,
  PaginatedResponse,
  Task,
  TaskOutputChunk,
  TaskPriority,
  TaskStatus,
  TaskType,
} from '@/types/admin';

/**
 * Hooks for the per-user ``/api/v1/tasks`` endpoints.
 *
 * The legacy admin views continue to consume the cross-user admin
 * endpoints from ``useAdmin.ts``; these hooks drive the dedicated
 * ``/tasks`` page which only shows the caller's own work.
 */

const TASK_KEY = ['tasks'] as const;

export interface TaskListParams {
  page?: number;
  pageSize?: number;
  status?: TaskStatus;
  task_type?: TaskType;
  priority?: TaskPriority;
  flow_id?: string;
}

export function useUserTasks(params: TaskListParams) {
  return useQuery({
    queryKey: [...TASK_KEY, 'list', params],
    queryFn: () =>
      apiClient.get<PaginatedResponse<Task>>('/tasks', {
        page: params.page,
        page_size: params.pageSize,
        status: params.status,
        task_type: params.task_type,
        priority: params.priority,
        flow_id: params.flow_id,
      } as Record<string, string | number | boolean | undefined>),
    refetchInterval: 5000,
  });
}

export function useUserTask(taskId: string | null | undefined) {
  return useQuery({
    queryKey: [...TASK_KEY, 'detail', taskId],
    queryFn: () => apiClient.get<Task>(`/tasks/${taskId}`),
    enabled: Boolean(taskId),
    refetchInterval: (query) => {
      const task = query.state.data as Task | undefined;
      if (!task) return 3000;
      return task.status === 'running' || task.status === 'pending' || task.status === 'queued'
        ? 2000
        : false;
    },
  });
}

export function useTaskOutput(taskId: string | null | undefined, offset: number) {
  return useQuery({
    queryKey: [...TASK_KEY, 'output', taskId, offset],
    queryFn: () =>
      apiClient.get<TaskOutputChunk>(`/tasks/${taskId}/output`, { offset }),
    enabled: Boolean(taskId),
    // Poll aggressively while the task is still running; stop once
    // ``is_done`` flips so we do not hammer the server for completed
    // tasks the user is just scrolling back through.
    refetchInterval: (query) => {
      const chunk = query.state.data as TaskOutputChunk | undefined;
      if (!chunk) return 1000;
      return chunk.is_done ? false : 1000;
    },
  });
}

export function useCreateAgentRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AgentRunRequest) =>
      apiClient.post<AgentRunResponse>('/tasks/agent-runs', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TASK_KEY });
    },
  });
}

export function useKillUserTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) =>
      apiClient.post<{
        task_id: string;
        killed: boolean;
        previous_status: string;
        message: string;
      }>(`/tasks/${taskId}/kill`),
    onSuccess: (_res, taskId) => {
      queryClient.invalidateQueries({ queryKey: TASK_KEY });
      queryClient.invalidateQueries({ queryKey: [...TASK_KEY, 'detail', taskId] });
    },
  });
}

export function useCancelUserTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => apiClient.delete(`/tasks/${taskId}`),
    onSuccess: (_res, taskId) => {
      queryClient.invalidateQueries({ queryKey: TASK_KEY });
      queryClient.invalidateQueries({ queryKey: [...TASK_KEY, 'detail', taskId] });
    },
  });
}
