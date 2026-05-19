import { create } from 'zustand';
import type { ModelProvider, Tool, RuleSetInfo, Task } from '@/types/admin';

type AdminTab = 'providers' | 'tools' | 'rules' | 'tasks';

interface AdminState {
  activeTab: AdminTab;
  setActiveTab: (tab: AdminTab) => void;

  selectedProvider: ModelProvider | null;
  setSelectedProvider: (provider: ModelProvider | null) => void;
  isProviderModalOpen: boolean;
  setProviderModalOpen: (open: boolean) => void;

  selectedTool: Tool | null;
  setSelectedTool: (tool: Tool | null) => void;
  isToolConfigModalOpen: boolean;
  setToolConfigModalOpen: (open: boolean) => void;

  selectedRule: RuleSetInfo | null;
  setSelectedRule: (rule: RuleSetInfo | null) => void;
  isRuleModalOpen: boolean;
  setRuleModalOpen: (open: boolean) => void;

  selectedTask: Task | null;
  setSelectedTask: (task: Task | null) => void;
  isTaskDetailModalOpen: boolean;
  setTaskDetailModalOpen: (open: boolean) => void;

  taskStatusFilter: string;
  setTaskStatusFilter: (status: string) => void;
}

export const useAdminStore = create<AdminState>((set) => ({
  activeTab: 'providers',
  setActiveTab: (tab) => set({ activeTab: tab }),

  selectedProvider: null,
  setSelectedProvider: (provider) => set({ selectedProvider: provider }),
  isProviderModalOpen: false,
  setProviderModalOpen: (open) => set({ isProviderModalOpen: open }),

  selectedTool: null,
  setSelectedTool: (tool) => set({ selectedTool: tool }),
  isToolConfigModalOpen: false,
  setToolConfigModalOpen: (open) => set({ isToolConfigModalOpen: open }),

  selectedRule: null,
  setSelectedRule: (rule) => set({ selectedRule: rule }),
  isRuleModalOpen: false,
  setRuleModalOpen: (open) => set({ isRuleModalOpen: open }),

  selectedTask: null,
  setSelectedTask: (task) => set({ selectedTask: task }),
  isTaskDetailModalOpen: false,
  setTaskDetailModalOpen: (open) => set({ isTaskDetailModalOpen: open }),

  taskStatusFilter: 'all',
  setTaskStatusFilter: (status) => set({ taskStatusFilter: status }),
}));
