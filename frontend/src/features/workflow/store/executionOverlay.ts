import { create } from 'zustand';

/** Node execution status mirrored from the backend `ProgressRegistry`. */
export type NodeRunStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'error'
  | 'blocked'
  | 'cached';

export interface NodeRunState {
  status: NodeRunStatus;
  /** 0..1 progress (for nodes that report intermediate progress). */
  progress?: number;
  /** Latest streamed preview row (agent activity, deltas, etc.). */
  preview?: unknown;
  error?: string;
}

export interface BlockedInfo {
  nodeId: string;
  /** Block tag, e.g. `awaiting_user_input` or `awaiting_review`. */
  tag: string;
  /** The agent's question (for awaiting_user_input pauses). */
  question?: string;
  checkpointId?: string;
}

interface ExecutionOverlayState {
  promptId: string | null;
  running: boolean;
  nodes: Record<string, NodeRunState>;
  /** Set when the run paused on a blocking node (resume affordance). */
  blocked: BlockedInfo | null;
  start: (promptId: string) => void;
  setNode: (nodeId: string, patch: Partial<NodeRunState>) => void;
  setBlocked: (info: BlockedInfo | null) => void;
  finish: () => void;
  reset: () => void;
}

/**
 * Holds the live execution overlay the canvas renders on top of nodes. Fed by
 * the workflow execution WebSocket (`/ws/executions/{prompt_id}`), mirroring
 * ComfyUI's progressive node highlighting.
 */
export const useExecutionOverlay = create<ExecutionOverlayState>((set) => ({
  promptId: null,
  running: false,
  nodes: {},
  blocked: null,
  start: (promptId) => set({ promptId, running: true, nodes: {}, blocked: null }),
  setNode: (nodeId, patch) =>
    set((state) => ({
      nodes: {
        ...state.nodes,
        [nodeId]: { status: 'pending', ...state.nodes[nodeId], ...patch },
      },
    })),
  setBlocked: (info) => set({ blocked: info }),
  finish: () => set({ running: false }),
  reset: () => set({ promptId: null, running: false, nodes: {}, blocked: null }),
}));
