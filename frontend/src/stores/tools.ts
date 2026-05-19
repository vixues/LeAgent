import { create } from 'zustand';
import type { Tool, ToolCategory } from '@/types/admin';

interface ToolsStore {
  search: string;
  setSearch: (search: string) => void;
  selectedCategory: ToolCategory | 'all';
  setSelectedCategory: (category: ToolCategory | 'all') => void;
  selectedTool: Tool | null;
  setSelectedTool: (tool: Tool | null) => void;
  isConfigModalOpen: boolean;
  setConfigModalOpen: (open: boolean) => void;
}

export const useToolsStore = create<ToolsStore>((set) => ({
  search: '',
  setSearch: (search) => set({ search }),
  selectedCategory: 'all',
  setSelectedCategory: (selectedCategory) => set({ selectedCategory }),
  selectedTool: null,
  setSelectedTool: (selectedTool) => set({ selectedTool }),
  isConfigModalOpen: false,
  setConfigModalOpen: (isConfigModalOpen) => set({ isConfigModalOpen }),
}));
