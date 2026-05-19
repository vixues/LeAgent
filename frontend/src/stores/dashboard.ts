import { create } from 'zustand';

type TimeRange = 'today' | 'week' | 'month';

interface DashboardStore {
  timeRange: TimeRange;
  setTimeRange: (range: TimeRange) => void;
  selectedTaskId: string | null;
  setSelectedTaskId: (id: string | null) => void;
}

export const useDashboardStore = create<DashboardStore>((set) => ({
  timeRange: 'today',
  setTimeRange: (timeRange) => set({ timeRange }),
  selectedTaskId: null,
  setSelectedTaskId: (selectedTaskId) => set({ selectedTaskId }),
}));
