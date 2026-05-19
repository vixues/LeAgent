import { useQuery, useMutation, useQueryClient, UseQueryOptions } from '@tanstack/react-query';
import { apiClient, ApiError } from '@/api/client';
import { URL_KEYS, QUERY_KEYS, CACHE_TIME } from '../../helpers/constants';

// ---- Types ----

export interface CronJobInfo {
  id: string;
  name: string;
  description?: string;
  job_type: 'flow' | 'task' | 'webhook' | 'script';
  cron_expression: string;
  status: 'active' | 'paused' | 'running' | 'failed' | 'disabled';
  enabled: boolean;
  last_run_at?: string;
  next_run_at?: string;
  run_count: number;
  success_count: number;
  error_count: number;
  success_rate: number;
  consecutive_failures: number;
  next_runs: string[];
  created_at: string;
  updated_at: string;
}

export interface CronJobDetail extends CronJobInfo {
  target_id?: string;
  payload: Record<string, unknown>;
  last_run_status?: string;
  last_error?: string;
  timezone: string;
  max_retries: number;
  timeout_sec: number;
  notify_on_start: boolean;
  notify_on_complete: boolean;
  notify_on_fail: boolean;
  tags: string[];
}

export interface CronJobExecution {
  id: string;
  job_id: string;
  job_name: string;
  execution_number: number;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'timeout' | 'cancelled' | 'skipped';
  trigger_type: string;
  scheduled_at?: string;
  started_at?: string;
  completed_at?: string;
  workflow_id?: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  error?: string;
  error_type?: string;
  retry_count: number;
  duration_ms: number;
  node_count: number;
}

export interface CronJobListResponse {
  jobs: CronJobInfo[];
  total: number;
}

export interface CronJobStats {
  job_id: string;
  name: string;
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  success_rate: number;
  avg_duration_ms: number;
  last_run_at?: string;
  next_run_at?: string;
}

export interface CronSystemStats {
  total_jobs: number;
  active_jobs: number;
  paused_jobs: number;
  failed_jobs: number;
  running_executions: number;
  total_runs_all_jobs: number;
  scheduler_running: boolean;
  next_runs: Array<{ job_id: string; name: string; next_run: string }>;
}

export interface CronJobNextRunsResponse {
  cron_expression: string;
  next_runs: string[];
}

export interface CreateCronJobInput {
  name: string;
  description?: string;
  job_type: 'flow' | 'task' | 'webhook' | 'script';
  cron_expression: string;
  target_id?: string;
  payload?: Record<string, unknown>;
  enabled?: boolean;
  timezone?: string;
  max_retries?: number;
  timeout_sec?: number;
  notify_on_start?: boolean;
  notify_on_complete?: boolean;
  notify_on_fail?: boolean;
  tags?: string[];
}

export interface UpdateCronJobInput {
  id: string;
  name?: string;
  description?: string;
  cron_expression?: string;
  target_id?: string;
  payload?: Record<string, unknown>;
  enabled?: boolean;
  timezone?: string;
  max_retries?: number;
  timeout_sec?: number;
  notify_on_start?: boolean;
  notify_on_complete?: boolean;
  notify_on_fail?: boolean;
  tags?: string[];
}

// ---- Queries ----

export interface CronJobFilters {
  status?: string;
  job_type?: string;
  search?: string;
}

export const useCronJobs = (
  filters?: CronJobFilters,
  options?: Omit<UseQueryOptions<CronJobListResponse, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<CronJobListResponse, ApiError>({
    queryKey: [...QUERY_KEYS.CRON_JOBS, filters],
    queryFn: async () => {
      return apiClient.get<CronJobListResponse>(URL_KEYS.CRON_JOBS, filters as Record<string, string | number | boolean | undefined>);
    },
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    ...options,
  });
};

export const useCronJob = (
  jobId: string,
  options?: Omit<UseQueryOptions<CronJobDetail, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<CronJobDetail, ApiError>({
    queryKey: QUERY_KEYS.CRON_JOB(jobId),
    queryFn: async () => {
      return apiClient.get<CronJobDetail>(URL_KEYS.CRON_JOB_BY_ID(jobId));
    },
    enabled: !!jobId,
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    ...options,
  });
};

export const useCronJobHistory = (
  jobId: string,
  limit?: number,
  options?: Omit<UseQueryOptions<{ executions: CronJobExecution[]; total: number }, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<{ executions: CronJobExecution[]; total: number }, ApiError>({
    queryKey: [...QUERY_KEYS.CRON_JOB_HISTORY(jobId), limit],
    queryFn: async () => {
      return apiClient.get<{ executions: CronJobExecution[]; total: number }>(
        URL_KEYS.CRON_JOB_HISTORY(jobId),
        { limit: limit || 50 },
      );
    },
    enabled: !!jobId,
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    ...options,
  });
};

export const useCronJobStats = (
  jobId: string,
  options?: Omit<UseQueryOptions<CronJobStats, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<CronJobStats, ApiError>({
    queryKey: QUERY_KEYS.CRON_JOB_STATS(jobId),
    queryFn: async () => {
      return apiClient.get<CronJobStats>(URL_KEYS.CRON_JOB_STATS(jobId));
    },
    enabled: !!jobId,
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    ...options,
  });
};

export const useCronJobNextRuns = (
  jobId: string,
  count?: number,
  options?: Omit<UseQueryOptions<CronJobNextRunsResponse, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<CronJobNextRunsResponse, ApiError>({
    queryKey: [...QUERY_KEYS.CRON_JOB_NEXT_RUNS(jobId), count ?? 8],
    queryFn: async () => {
      return apiClient.get<CronJobNextRunsResponse>(URL_KEYS.CRON_JOB_NEXT_RUNS(jobId), {
        count: count ?? 8,
      });
    },
    enabled: !!jobId,
    staleTime: CACHE_TIME.STALE_TIME_MEDIUM,
    ...options,
  });
};

export const useCronHealth = (
  options?: Omit<UseQueryOptions<Record<string, unknown>, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<Record<string, unknown>, ApiError>({
    queryKey: QUERY_KEYS.CRON_HEALTH,
    queryFn: async () => {
      return apiClient.get<Record<string, unknown>>(URL_KEYS.CRON_HEALTH);
    },
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    refetchInterval: 30000,
    ...options,
  });
};

export const useCronSystemStats = (
  options?: Omit<UseQueryOptions<CronSystemStats, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<CronSystemStats, ApiError>({
    queryKey: QUERY_KEYS.CRON_STATS,
    queryFn: async () => {
      return apiClient.get<CronSystemStats>(URL_KEYS.CRON_STATS);
    },
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    refetchInterval: 30000,
    ...options,
  });
};

export const usePreviewNextRuns = (
  cronExpression: string,
  count?: number,
  options?: Omit<UseQueryOptions<{ cron_expression: string; next_runs: string[] }, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<{ cron_expression: string; next_runs: string[] }, ApiError>({
    queryKey: ['cron', 'preview', cronExpression, count],
    queryFn: async () => {
      return apiClient.get<{ cron_expression: string; next_runs: string[] }>(
        URL_KEYS.CRON_PREVIEW_NEXT_RUNS,
        { cron_expression: cronExpression, count: count || 5 },
      );
    },
    enabled: !!cronExpression && cronExpression.trim().split(/\s+/).length >= 5,
    staleTime: CACHE_TIME.STALE_TIME_MEDIUM,
    ...options,
  });
};

// ---- Mutations ----

export const useCreateCronJob = () => {
  const queryClient = useQueryClient();
  return useMutation<CronJobDetail, ApiError, CreateCronJobInput>({
    mutationFn: async (input) => {
      return apiClient.post<CronJobDetail>(URL_KEYS.CRON_JOBS, input);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CRON_JOBS });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CRON_STATS });
    },
  });
};

export const useUpdateCronJob = () => {
  const queryClient = useQueryClient();
  return useMutation<CronJobDetail, ApiError, UpdateCronJobInput>({
    mutationFn: async ({ id, ...data }) => {
      return apiClient.put<CronJobDetail>(URL_KEYS.CRON_JOB_BY_ID(id), data);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CRON_JOBS });
      queryClient.setQueryData(QUERY_KEYS.CRON_JOB(data.id), data);
    },
  });
};

export const useDeleteCronJob = () => {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: async (jobId) => {
      await apiClient.delete(URL_KEYS.CRON_JOB_BY_ID(jobId));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CRON_JOBS });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CRON_STATS });
    },
  });
};

export const usePauseCronJob = () => {
  const queryClient = useQueryClient();
  return useMutation<{ job_id: string; status: string }, ApiError, string>({
    mutationFn: async (jobId) => {
      return apiClient.post<{ job_id: string; status: string }>(URL_KEYS.CRON_JOB_PAUSE(jobId));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CRON_JOBS });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CRON_STATS });
    },
  });
};

export const useResumeCronJob = () => {
  const queryClient = useQueryClient();
  return useMutation<{ job_id: string; status: string }, ApiError, string>({
    mutationFn: async (jobId) => {
      return apiClient.post<{ job_id: string; status: string }>(URL_KEYS.CRON_JOB_RESUME(jobId));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CRON_JOBS });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CRON_STATS });
    },
  });
};

export const useTriggerCronJob = () => {
  const queryClient = useQueryClient();
  return useMutation<{ job_id: string; task_id: string; status: string; message: string }, ApiError, string>({
    mutationFn: async (jobId) => {
      return apiClient.post<{ job_id: string; task_id: string; status: string; message: string }>(URL_KEYS.CRON_JOB_RUN(jobId));
    },
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CRON_JOB_HISTORY(jobId) });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CRON_JOBS });
    },
  });
};

export const useCloneCronJob = () => {
  const queryClient = useQueryClient();
  return useMutation<CronJobDetail, ApiError, { jobId: string; newName?: string }>({
    mutationFn: async ({ jobId, newName }) => {
      return apiClient.post<CronJobDetail>(
        URL_KEYS.CRON_JOB_CLONE(jobId),
        null,
        { params: newName ? { new_name: newName } : undefined },
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.CRON_JOBS });
    },
  });
};
