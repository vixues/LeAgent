import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  Node,
  Edge,
  Connection,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  NodeChange,
  EdgeChange,
  XYPosition,
} from '@xyflow/react';

export interface FlowNodeData extends Record<string, unknown> {
  label: string;
  icon: string;
  category: string;
  description?: string;
  parameters?: Record<string, unknown>;
  inputs?: string[];
  outputs?: string[];
}

export type FlowNode = Node<FlowNodeData>;
export type FlowEdge = Edge;

interface HistoryState {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

interface FlowState {
  flowId: string | null;
  flowName: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
  selectedNodeId: string | null;
  isDirty: boolean;
  history: HistoryState[];
  historyIndex: number;

  setFlowId: (id: string | null) => void;
  setFlowName: (name: string) => void;
  setNodes: (nodes: FlowNode[]) => void;
  setEdges: (edges: FlowEdge[]) => void;
  onNodesChange: (changes: NodeChange<FlowNode>[]) => void;
  onEdgesChange: (changes: EdgeChange<FlowEdge>[]) => void;
  onConnect: (connection: Connection) => void;
  
  addNode: (node: FlowNode) => void;
  removeNode: (nodeId: string) => void;
  updateNode: (nodeId: string, data: Partial<FlowNodeData>) => void;
  updateNodePosition: (nodeId: string, position: XYPosition) => void;
  
  addEdge: (edge: FlowEdge) => void;
  removeEdge: (edgeId: string) => void;
  
  selectNode: (nodeId: string | null) => void;
  
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
  
  saveToHistory: () => void;
  clearHistory: () => void;
  
  loadFlow: (flow: {
    id: string | null;
    name: string;
    nodes: FlowNode[];
    edges: FlowEdge[];
  }) => void;
  getFlowData: () => {
    id: string | null;
    name: string;
    nodes: FlowNode[];
    edges: FlowEdge[];
  };
  resetFlow: () => void;
  markClean: () => void;
}

const MAX_HISTORY_SIZE = 50;

function normalizeNode(raw: unknown): FlowNode | null {
  if (!raw || typeof raw !== 'object') return null;
  const n = raw as Record<string, unknown>;

  const id = typeof n.id === 'string' ? n.id : n.id != null ? String(n.id) : '';
  if (!id) return null;

  const pos = n.position as { x?: unknown; y?: unknown } | undefined;
  const x = typeof pos?.x === 'number' && Number.isFinite(pos.x) ? pos.x : 0;
  const y = typeof pos?.y === 'number' && Number.isFinite(pos.y) ? pos.y : 0;

  const rawData = (n.data ?? {}) as Record<string, unknown>;
  const data: FlowNodeData = {
    label: typeof rawData.label === 'string' ? rawData.label : id,
    icon: typeof rawData.icon === 'string' ? rawData.icon : 'default',
    category: typeof rawData.category === 'string' ? rawData.category : 'default',
    description: typeof rawData.description === 'string' ? rawData.description : undefined,
    parameters:
      rawData.parameters && typeof rawData.parameters === 'object'
        ? (rawData.parameters as Record<string, unknown>)
        : undefined,
    inputs: Array.isArray(rawData.inputs) ? (rawData.inputs as string[]) : undefined,
    outputs: Array.isArray(rawData.outputs) ? (rawData.outputs as string[]) : undefined,
  };

  return {
    ...(n as object),
    id,
    type: typeof n.type === 'string' ? n.type : 'generic',
    position: { x, y },
    data,
  } as FlowNode;
}

function normalizeEdge(raw: unknown): FlowEdge | null {
  if (!raw || typeof raw !== 'object') return null;
  const e = raw as Record<string, unknown>;
  const id = typeof e.id === 'string' ? e.id : e.id != null ? String(e.id) : '';
  const source = typeof e.source === 'string' ? e.source : '';
  const target = typeof e.target === 'string' ? e.target : '';
  if (!id || !source || !target) return null;
  return { ...(e as object), id, source, target } as FlowEdge;
}

function normalizeNodes(raw: unknown): FlowNode[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map(normalizeNode)
    .filter((n): n is FlowNode => n !== null);
}

function normalizeEdges(raw: unknown): FlowEdge[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map(normalizeEdge)
    .filter((e): e is FlowEdge => e !== null);
}

const initialState = {
  flowId: null,
  flowName: 'Untitled Flow',
  nodes: [],
  edges: [],
  selectedNodeId: null,
  isDirty: false,
  history: [],
  historyIndex: -1,
};

export const useFlowStore = create<FlowState>()(
  persist(
    (set, get) => ({
      ...initialState,

      setFlowId: (id) => set({ flowId: id }),

      setFlowName: (name) => {
        set({ flowName: name, isDirty: true });
      },
      
      setNodes: (nodes) => {
        set({ nodes, isDirty: true });
      },
      
      setEdges: (edges) => {
        set({ edges, isDirty: true });
      },
      
      onNodesChange: (changes) => {
        const { nodes } = get();
        const updatedNodes = applyNodeChanges(changes, nodes) as FlowNode[];
        set({ nodes: updatedNodes, isDirty: true });
      },
      
      onEdgesChange: (changes) => {
        const { edges } = get();
        const updatedEdges = applyEdgeChanges(changes, edges);
        set({ edges: updatedEdges, isDirty: true });
      },
      
      onConnect: (connection) => {
        const { edges, saveToHistory } = get();
        saveToHistory();
        const newEdge: FlowEdge = {
          ...connection,
          id: `edge-${connection.source}-${connection.target}-${Date.now()}`,
          type: 'default',
        };
        set({ edges: addEdge(newEdge, edges), isDirty: true });
      },
      
      addNode: (node) => {
        const { nodes, saveToHistory } = get();
        saveToHistory();
        set({ nodes: [...nodes, node], isDirty: true });
      },
      
      removeNode: (nodeId) => {
        const { nodes, edges, saveToHistory, selectedNodeId } = get();
        saveToHistory();
        set({
          nodes: nodes.filter((n) => n.id !== nodeId),
          edges: edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
          selectedNodeId: selectedNodeId === nodeId ? null : selectedNodeId,
          isDirty: true,
        });
      },
      
      updateNode: (nodeId, data) => {
        const { nodes, saveToHistory } = get();
        saveToHistory();
        set({
          nodes: nodes.map((n) =>
            n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n
          ),
          isDirty: true,
        });
      },
      
      updateNodePosition: (nodeId, position) => {
        const { nodes } = get();
        set({
          nodes: nodes.map((n) =>
            n.id === nodeId ? { ...n, position } : n
          ),
          isDirty: true,
        });
      },
      
      addEdge: (edge) => {
        const { edges, saveToHistory } = get();
        saveToHistory();
        set({ edges: [...edges, edge], isDirty: true });
      },
      
      removeEdge: (edgeId) => {
        const { edges, saveToHistory } = get();
        saveToHistory();
        set({
          edges: edges.filter((e) => e.id !== edgeId),
          isDirty: true,
        });
      },
      
      selectNode: (nodeId) => set({ selectedNodeId: nodeId }),
      
      undo: () => {
        const { history, historyIndex } = get();
        if (historyIndex > 0) {
          const prevState = history[historyIndex - 1];
          if (prevState) {
            set({
              nodes: prevState.nodes,
              edges: prevState.edges,
              historyIndex: historyIndex - 1,
              isDirty: true,
            });
          }
        }
      },
      
      redo: () => {
        const { history, historyIndex } = get();
        if (historyIndex < history.length - 1) {
          const nextState = history[historyIndex + 1];
          if (nextState) {
            set({
              nodes: nextState.nodes,
              edges: nextState.edges,
              historyIndex: historyIndex + 1,
              isDirty: true,
            });
          }
        }
      },
      
      canUndo: () => {
        const { historyIndex } = get();
        return historyIndex > 0;
      },
      
      canRedo: () => {
        const { history, historyIndex } = get();
        return historyIndex < history.length - 1;
      },
      
      saveToHistory: () => {
        const { nodes, edges, history, historyIndex } = get();
        const newHistory = history.slice(0, historyIndex + 1);
        newHistory.push({ nodes: [...nodes], edges: [...edges] });
        
        if (newHistory.length > MAX_HISTORY_SIZE) {
          newHistory.shift();
        }
        
        set({
          history: newHistory,
          historyIndex: newHistory.length - 1,
        });
      },
      
      clearHistory: () => {
        set({ history: [], historyIndex: -1 });
      },
      
      loadFlow: (flow) => {
        const nodes = normalizeNodes(flow.nodes);
        const edges = normalizeEdges(flow.edges);
        const fid = flow.id && String(flow.id).length > 0 ? String(flow.id) : null;
        set({
          flowId: fid,
          flowName: flow.name,
          nodes,
          edges,
          isDirty: false,
          history: [{ nodes, edges }],
          historyIndex: 0,
          selectedNodeId: null,
        });
      },

      getFlowData: () => {
        const { flowId, flowName, nodes, edges } = get();
        return { id: flowId, name: flowName, nodes, edges };
      },
      
      resetFlow: () => {
        set({
          ...initialState,
          history: [{ nodes: [], edges: [] }],
          historyIndex: 0,
        });
      },
      
      markClean: () => set({ isDirty: false }),
    }),
    {
      name: 'leagent-flow',
      partialize: (state) => ({
        flowId: state.flowId,
        flowName: state.flowName,
        nodes: state.nodes,
        edges: state.edges,
      }),
      merge: (persistedState, currentState) => {
        const p = persistedState as Partial<
          Pick<FlowState, 'flowId' | 'flowName' | 'nodes' | 'edges'>
        > | null;
        if (!p) return currentState;
        return {
          ...currentState,
          ...p,
          nodes: normalizeNodes(p.nodes),
          edges: normalizeEdges(p.edges),
        };
      },
    }
  )
);
