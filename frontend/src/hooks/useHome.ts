import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/api/client';

interface Flow {
  id: string;
  name: string;
  description?: string;
  status: 'draft' | 'active' | 'paused' | 'error';
  nodeCount: number;
  createdAt: string;
  updatedAt: string;
}

interface HomeStats {
  totalFlows: number;
  runningTasks: number;
  completedToday: number;
  successRate: number;
}

export function useRecentFlows(limit = 10) {
  return useQuery({
    queryKey: ['home', 'recent-flows', limit],
    queryFn: async () => {
      return apiClient.get<Flow[]>('/workflow/flows/recent', { limit });
    },
  });
}

export function useHomeStats() {
  return useQuery({
    queryKey: ['home', 'stats'],
    queryFn: async () => {
      return apiClient.get<HomeStats>('/stats/home');
    },
    refetchInterval: 30000,
  });
}
