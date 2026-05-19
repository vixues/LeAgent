import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface FlowLog {
  timestamp: string;
  level: 'info' | 'warn' | 'error' | 'debug';
  message: string;
  nodeId?: string;
  data?: unknown;
}

export interface FlowOutput {
  success: boolean;
  result?: unknown;
  error?: string;
  duration?: string;
  logs?: FlowLog[];
  nodeResults?: Record<string, { output: unknown; status: string }>;
}

export interface PlaygroundInput {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'json' | 'file';
  value: unknown;
  required?: boolean;
}

interface PlaygroundState {
  isOpen: boolean;
  isFullscreen: boolean;
  selectedFlowId: string | null;
  inputs: Record<string, unknown>;
  inputDefinitions: PlaygroundInput[];
  output: FlowOutput | null;
  isRunning: boolean;
  executionHistory: Array<{
    id: string;
    flowId: string;
    inputs: Record<string, unknown>;
    output: FlowOutput;
    timestamp: string;
  }>;
  maxHistorySize: number;

  open: () => void;
  close: () => void;
  toggle: () => void;
  setIsOpen: (isOpen: boolean) => void;
  
  enterFullscreen: () => void;
  exitFullscreen: () => void;
  toggleFullscreen: () => void;
  setIsFullscreen: (isFullscreen: boolean) => void;
  
  setSelectedFlowId: (id: string | null) => void;
  setInputs: (inputs: Record<string, unknown>) => void;
  setInputValue: (name: string, value: unknown) => void;
  setInputDefinitions: (definitions: PlaygroundInput[]) => void;
  clearInputs: () => void;
  
  setOutput: (output: FlowOutput | null) => void;
  appendLog: (log: FlowLog) => void;
  clearOutput: () => void;
  
  setIsRunning: (running: boolean) => void;
  
  addToHistory: (execution: { flowId: string; inputs: Record<string, unknown>; output: FlowOutput }) => void;
  clearHistory: () => void;
  getHistoryForFlow: (flowId: string) => PlaygroundState['executionHistory'];
  
  reset: () => void;
}

const generateId = () => Math.random().toString(36).substring(2, 11);

export const usePlaygroundStore = create<PlaygroundState>()(
  persist(
    (set, get) => ({
      isOpen: false,
      isFullscreen: false,
      selectedFlowId: null,
      inputs: {},
      inputDefinitions: [],
      output: null,
      isRunning: false,
      executionHistory: [],
      maxHistorySize: 50,

      open: () => set({ isOpen: true }),
      close: () => set({ isOpen: false, isFullscreen: false }),
      toggle: () => set((state) => ({ isOpen: !state.isOpen })),
      setIsOpen: (isOpen) => set({ isOpen }),

      enterFullscreen: () => set({ isFullscreen: true, isOpen: true }),
      exitFullscreen: () => set({ isFullscreen: false }),
      toggleFullscreen: () => set((state) => ({ 
        isFullscreen: !state.isFullscreen,
        isOpen: true,
      })),
      setIsFullscreen: (isFullscreen) => set({ isFullscreen }),

      setSelectedFlowId: (selectedFlowId) => set({ 
        selectedFlowId,
        inputs: {},
        output: null,
      }),

      setInputs: (inputs) => set({ inputs }),
      
      setInputValue: (name, value) => set((state) => ({
        inputs: { ...state.inputs, [name]: value },
      })),

      setInputDefinitions: (inputDefinitions) => set({ inputDefinitions }),

      clearInputs: () => set({ inputs: {} }),

      setOutput: (output) => set({ output }),

      appendLog: (log) => set((state) => {
        if (!state.output) {
          return { output: { success: true, logs: [log] } };
        }
        return {
          output: {
            ...state.output,
            logs: [...(state.output.logs || []), log],
          },
        };
      }),

      clearOutput: () => set({ output: null }),

      setIsRunning: (isRunning) => set({ isRunning }),

      addToHistory: ({ flowId, inputs, output }) => {
        const { maxHistorySize } = get();
        set((state) => {
          const newEntry = {
            id: generateId(),
            flowId,
            inputs,
            output,
            timestamp: new Date().toISOString(),
          };
          
          let history = [...state.executionHistory, newEntry];
          if (history.length > maxHistorySize) {
            history = history.slice(-maxHistorySize);
          }
          
          return { executionHistory: history };
        });
      },

      clearHistory: () => set({ executionHistory: [] }),

      getHistoryForFlow: (flowId) =>
        get().executionHistory.filter((e) => e.flowId === flowId),

      reset: () => set({
        isOpen: false,
        isFullscreen: false,
        selectedFlowId: null,
        inputs: {},
        inputDefinitions: [],
        output: null,
        isRunning: false,
      }),
    }),
    {
      name: 'leagent-playground',
      partialize: (state) => ({
        executionHistory: state.executionHistory,
      }),
    }
  )
);
