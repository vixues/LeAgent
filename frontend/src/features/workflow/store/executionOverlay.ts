import { create } from 'zustand';

import type { GenUiTreeV1 } from '@/types/genUi';

/** Node execution status mirrored from the backend `ProgressRegistry`. */
export type NodeRunStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'error'
  | 'blocked'
  | 'cached'
  | 'skipped';

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
  /** Raw `data.ui` payload from the `execution_blocked` event. */
  ui?: Record<string, unknown>;
}

interface ExecutionOverlayState {
  promptId: string | null;
  running: boolean;
  nodes: Record<string, NodeRunState>;
  /** Set when the run paused on a blocking node (resume affordance). */
  blocked: BlockedInfo | null;
  /** Resolved `WorkflowDocument.outputs` from the terminal event. */
  outputs: Record<string, unknown> | null;
  /** Explicit `NodeOutput.ui.gen_ui` trees collected from `executed` events. */
  genUiTrees: GenUiTreeV1[];
  errors: string[];
  start: (promptId: string) => void;
  setNode: (nodeId: string, patch: Partial<NodeRunState>) => void;
  setBlocked: (info: BlockedInfo | null) => void;
  addGenUiTree: (tree: GenUiTreeV1) => void;
  finish: (result?: { outputs?: Record<string, unknown>; errors?: string[] }) => void;
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
  outputs: null,
  genUiTrees: [],
  errors: [],
  start: (promptId) =>
    set({
      promptId,
      running: true,
      nodes: {},
      blocked: null,
      outputs: null,
      genUiTrees: [],
      errors: [],
    }),
  setNode: (nodeId, patch) =>
    set((state) => ({
      nodes: {
        ...state.nodes,
        [nodeId]: { status: 'pending', ...state.nodes[nodeId], ...patch },
      },
    })),
  setBlocked: (info) => set({ blocked: info }),
  addGenUiTree: (tree) =>
    set((state) => ({ genUiTrees: [...state.genUiTrees, tree] })),
  finish: (result) =>
    set((state) => ({
      running: false,
      outputs: result?.outputs ?? state.outputs,
      errors: result?.errors ?? state.errors,
    })),
  reset: () =>
    set({
      promptId: null,
      running: false,
      nodes: {},
      blocked: null,
      outputs: null,
      genUiTrees: [],
      errors: [],
    }),
}));
