import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { apiClient } from '@/api/client';
import type { FlowData, FlowNode, FlowEdge } from '@/types/flow';

interface FlowSnapshot {
  nodes: FlowNode[];
  edges: FlowEdge[];
  timestamp: number;
}

interface FlowsManagerState {
  flows: FlowData[];
  currentFlowId: string | null;
  isLoading: boolean;
  error: string | null;
  
  undoStack: FlowSnapshot[];
  redoStack: FlowSnapshot[];
  maxHistorySize: number;

  setFlows: (flows: FlowData[]) => void;
  setCurrentFlowId: (id: string | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  
  fetchFlows: () => Promise<void>;
  fetchFlow: (id: string) => Promise<FlowData | null>;
  createFlow: (flow: Partial<FlowData>) => Promise<FlowData>;
  updateFlow: (id: string, updates: Partial<FlowData>) => Promise<FlowData>;
  deleteFlow: (id: string) => Promise<void>;
  duplicateFlow: (id: string, newName?: string) => Promise<FlowData>;
  
  getCurrentFlow: () => FlowData | null;
  getFlowById: (id: string) => FlowData | null;
  
  pushToUndoStack: (snapshot: FlowSnapshot) => void;
  undo: () => FlowSnapshot | null;
  redo: () => FlowSnapshot | null;
  canUndo: () => boolean;
  canRedo: () => boolean;
  clearHistory: () => void;
  
  importFlow: (flowJson: string) => Promise<FlowData>;
  exportFlow: (id: string) => string | null;
}

export const useFlowsManagerStore = create<FlowsManagerState>()(
  persist(
    (set, get) => ({
      flows: [],
      currentFlowId: null,
      isLoading: false,
      error: null,
      undoStack: [],
      redoStack: [],
      maxHistorySize: 50,

      setFlows: (flows) => set({ flows }),
      setCurrentFlowId: (currentFlowId) => set({ currentFlowId }),
      setLoading: (isLoading) => set({ isLoading }),
      setError: (error) => set({ error }),

      fetchFlows: async () => {
        set({ isLoading: true, error: null });
        try {
          const res = await apiClient.get<{ items: FlowData[]; total: number }>('/workflow/flows');
          set({ flows: res.items, isLoading: false });
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to fetch flows';
          set({ error: message, isLoading: false });
          throw err;
        }
      },

      fetchFlow: async (id) => {
        set({ isLoading: true, error: null });
        try {
          const flow = await apiClient.get<FlowData>(`/workflow/flows/${id}`);
          set((state) => ({
            flows: state.flows.some((f) => f.id === id)
              ? state.flows.map((f) => (f.id === id ? flow : f))
              : [...state.flows, flow],
            isLoading: false,
          }));
          return flow;
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to fetch flow';
          set({ error: message, isLoading: false });
          return null;
        }
      },

      createFlow: async (flow) => {
        set({ isLoading: true, error: null });
        try {
          const newFlow = await apiClient.post<FlowData>('/workflow/flows', {
            name: flow.name || 'Untitled Flow',
            description: flow.description,
            nodes: flow.nodes || [],
            edges: flow.edges || [],
            tags: flow.tags || [],
          });
          set((state) => ({
            flows: [newFlow, ...state.flows],
            currentFlowId: newFlow.id,
            isLoading: false,
          }));
          return newFlow;
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to create flow';
          set({ error: message, isLoading: false });
          throw err;
        }
      },

      updateFlow: async (id, updates) => {
        set({ isLoading: true, error: null });
        try {
          const updatedFlow = await apiClient.put<FlowData>(`/workflow/flows/${id}`, updates);
          set((state) => ({
            flows: state.flows.map((f) => (f.id === id ? updatedFlow : f)),
            isLoading: false,
          }));
          return updatedFlow;
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to update flow';
          set({ error: message, isLoading: false });
          throw err;
        }
      },

      deleteFlow: async (id) => {
        set({ isLoading: true, error: null });
        try {
          await apiClient.delete(`/workflow/flows/${id}`);
          set((state) => ({
            flows: state.flows.filter((f) => f.id !== id),
            currentFlowId: state.currentFlowId === id ? null : state.currentFlowId,
            isLoading: false,
          }));
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to delete flow';
          set({ error: message, isLoading: false });
          throw err;
        }
      },

      duplicateFlow: async (id, newName) => {
        const flow = get().getFlowById(id);
        if (!flow) throw new Error('Flow not found');

        const duplicatedFlow = await get().createFlow({
          name: newName || `${flow.name} (Copy)`,
          description: flow.description,
          nodes: flow.nodes,
          edges: flow.edges,
          tags: flow.tags,
        });
        return duplicatedFlow;
      },

      getCurrentFlow: () => {
        const { flows, currentFlowId } = get();
        if (!currentFlowId) return null;
        return flows.find((f) => f.id === currentFlowId) || null;
      },

      getFlowById: (id) => {
        return get().flows.find((f) => f.id === id) || null;
      },

      pushToUndoStack: (snapshot) => {
        set((state) => {
          const newUndoStack = [...state.undoStack, snapshot];
          if (newUndoStack.length > state.maxHistorySize) {
            newUndoStack.shift();
          }
          return { undoStack: newUndoStack, redoStack: [] };
        });
      },

      undo: () => {
        const { undoStack, redoStack } = get();
        if (undoStack.length === 0) return null;

        const snapshot = undoStack[undoStack.length - 1]!;
        set({
          undoStack: undoStack.slice(0, -1),
          redoStack: [...redoStack, snapshot],
        });
        return snapshot;
      },

      redo: () => {
        const { undoStack, redoStack } = get();
        if (redoStack.length === 0) return null;

        const snapshot = redoStack[redoStack.length - 1]!;
        set({
          redoStack: redoStack.slice(0, -1),
          undoStack: [...undoStack, snapshot],
        });
        return snapshot;
      },

      canUndo: () => get().undoStack.length > 0,
      canRedo: () => get().redoStack.length > 0,

      clearHistory: () => {
        set({ undoStack: [], redoStack: [] });
      },

      importFlow: async (flowJson) => {
        try {
          const parsed = JSON.parse(flowJson) as Partial<FlowData>;
          if (!parsed.nodes || !parsed.edges) {
            throw new Error('Invalid flow format');
          }
          return await get().createFlow({
            name: parsed.name || 'Imported Flow',
            description: parsed.description,
            nodes: parsed.nodes,
            edges: parsed.edges,
            tags: parsed.tags,
          });
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to import flow';
          set({ error: message });
          throw new Error(message);
        }
      },

      exportFlow: (id) => {
        const flow = get().getFlowById(id);
        if (!flow) return null;
        return JSON.stringify({
          name: flow.name,
          description: flow.description,
          nodes: flow.nodes,
          edges: flow.edges,
          tags: flow.tags,
        }, null, 2);
      },
    }),
    {
      name: 'leagent-flows-manager',
      partialize: (state) => ({
        currentFlowId: state.currentFlowId,
      }),
    }
  )
);
