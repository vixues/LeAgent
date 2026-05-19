import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/api/client';
import { useDashboardStore } from '@/stores/dashboard';
import type { Task, PaginatedResponse, TaskStatus } from '@/types/admin';

interface DashboardStats {
  tasksToday: number;
  tasksChange: number;
  successRate: number;
  successRateChange: number;
  failedTasks: number;
  failedChange: number;
  avgDuration: string;
  durationChange: number;
}

interface UsageDataPoint {
  label: string;
  success: number;
  failed: number;
  date: string;
}

interface Activity {
  id: string;
  type: 'task_completed' | 'task_failed' | 'task_started' | 'workflow_paused' | 'warning';
  title: string;
  description: string;
  timestamp: string;
}

export function useDashboardStats() {
  const { timeRange } = useDashboardStore();
  
  return useQuery({
    queryKey: ['dashboard', 'stats', timeRange],
    queryFn: async () => {
      return apiClient.get<DashboardStats>('/stats/dashboard', { timeRange });
    },
    refetchInterval: 30000,
  });
}

export function useDashboardTasks(params: {
  page?: number;
  pageSize?: number;
  search?: string;
  status?: TaskStatus;
}) {
  return useQuery({
    queryKey: ['dashboard', 'tasks', params],
    queryFn: async () => {
      const { pageSize, ...rest } = params;
      const apiParams = { ...rest, page_size: pageSize };
      return apiClient.get<PaginatedResponse<Task>>('/tasks', apiParams);
    },
    refetchInterval: 10000,
  });
}

export function useUsageData(timeRange: 'today' | 'week' | 'month') {
  return useQuery({
    queryKey: ['dashboard', 'usage', timeRange],
    queryFn: async () => {
      return apiClient.get<UsageDataPoint[]>('/stats/usage', { timeRange });
    },
    refetchInterval: 60000,
  });
}

export function useActivityFeed(limit = 20) {
  return useQuery({
    queryKey: ['dashboard', 'activities', limit],
    queryFn: async () => {
      return apiClient.get<Activity[]>('/activities', { limit });
    },
    refetchInterval: 15000,
  });
}
