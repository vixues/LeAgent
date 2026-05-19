import { create } from 'zustand';

interface HomeStore {
  selectedPeriod: 'today' | 'week' | 'month';
  setSelectedPeriod: (period: 'today' | 'week' | 'month') => void;
}

export const useHomeStore = create<HomeStore>((set) => ({
  selectedPeriod: 'today',
  setSelectedPeriod: (period) => set({ selectedPeriod: period }),
}));
