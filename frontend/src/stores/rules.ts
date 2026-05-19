import { create } from 'zustand';
import type { RuleSetInfo } from '@/types/admin';

interface RulesStore {
  search: string;
  setSearch: (search: string) => void;
  selectedRule: RuleSetInfo | null;
  setSelectedRule: (rule: RuleSetInfo | null) => void;
  isEditorOpen: boolean;
  setEditorOpen: (open: boolean) => void;
  isTestPanelOpen: boolean;
  setTestPanelOpen: (open: boolean) => void;
}

export const useRulesStore = create<RulesStore>((set) => ({
  search: '',
  setSearch: (search) => set({ search }),
  selectedRule: null,
  setSelectedRule: (selectedRule) => set({ selectedRule }),
  isEditorOpen: false,
  setEditorOpen: (isEditorOpen) => set({ isEditorOpen }),
  isTestPanelOpen: false,
  setTestPanelOpen: (isTestPanelOpen) => set({ isTestPanelOpen }),
}));
