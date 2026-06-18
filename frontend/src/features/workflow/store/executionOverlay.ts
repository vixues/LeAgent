import { create } from 'zustand';

import type { GenUiTreeV1 } from '@/types/genUi';

import {
  appendAssetHistoryEntry,
  type AssetHistoryEntry,
  type AssetHistorySnapshot,
} from './assetHistory';

/** Node execution status mirrored from the backend `ProgressRegistry`. */
export type NodeRunStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'error'
  | 'blocked'
  | 'cached'
  | 'skipped';

export type OverlaySurface = 'editor' | 'chat';

export interface NodeRunState {
  status: NodeRunStatus;
  /** 0..1 progress (for nodes that report intermediate progress). */
  progress?: number;
  /** Latest streamed preview row (agent activity, deltas, etc.). */
  preview?: unknown;
  /**
   * GenUI asset tree emitted by the node on ``executed`` (``NodeOutput.ui.gen_ui``).
   * Drives the ComfyUI-style inline media thumbnail on the node card.
   */
  ui?: GenUiTreeV1 | null;
  /**
   * Node ``executed`` metadata (provider, quality_score, refine iteration,
   * engine, attempts…). Drives the art-node quality/refine badges.
   */
  metadata?: Record<string, unknown>;
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

export interface PromptOverlayState {
  running: boolean;
  nodes: Record<string, NodeRunState>;
  /** Chronological unique-file snapshots (refine re-runs append, passthrough deduped). */
  assetHistory: AssetHistoryEntry[];
  /** @deprecated Latest-only node order; prefer ``assetHistory``. */
  assetOrder: string[];
  blocked: BlockedInfo | null;
  outputs: Record<string, unknown> | null;
  genUiTrees: GenUiTreeV1[];
  errors: string[];
}

function emptyOverlay(): PromptOverlayState {
  return {
    running: false,
    nodes: {},
    assetHistory: [],
    assetOrder: [],
    blocked: null,
    outputs: null,
    genUiTrees: [],
    errors: [],
  };
}

function primaryOverlay(
  overlays: Record<string, PromptOverlayState>,
  editorActivePromptId: string | null,
): PromptOverlayState {
  if (!editorActivePromptId) return emptyOverlay();
  return overlays[editorActivePromptId] ?? emptyOverlay();
}

function cloneNodePatch(patch: Partial<NodeRunState>): Partial<NodeRunState> {
  const next: Partial<NodeRunState> = { ...patch };
  if (patch.metadata) {
    next.metadata = structuredClone(patch.metadata);
  }
  if (patch.ui) {
    next.ui = structuredClone(patch.ui);
  }
  return next;
}

function withEditorSync(
  overlays: Record<string, PromptOverlayState>,
  editorActivePromptId: string | null,
): {
  overlays: Record<string, PromptOverlayState>;
  editorActivePromptId: string | null;
  activePromptId: string | null;
  promptId: string | null;
  running: boolean;
  nodes: Record<string, NodeRunState>;
  assetHistory: AssetHistoryEntry[];
  assetOrder: string[];
  blocked: BlockedInfo | null;
  outputs: Record<string, unknown> | null;
  genUiTrees: GenUiTreeV1[];
  errors: string[];
} {
  const primary = primaryOverlay(overlays, editorActivePromptId);
  return {
    overlays,
    editorActivePromptId,
    activePromptId: editorActivePromptId,
    promptId: editorActivePromptId,
    running: primary.running,
    nodes: primary.nodes,
    assetHistory: primary.assetHistory,
    assetOrder: primary.assetOrder,
    blocked: primary.blocked,
    outputs: primary.outputs,
    genUiTrees: primary.genUiTrees,
    errors: primary.errors,
  };
}

interface ExecutionOverlayState {
  overlays: Record<string, PromptOverlayState>;
  /** Editor-scoped primary overlay; chat runs do not repoint this. */
  editorActivePromptId: string | null;
  activePromptId: string | null;
  promptId: string | null;
  running: boolean;
  nodes: Record<string, NodeRunState>;
  assetHistory: AssetHistoryEntry[];
  assetOrder: string[];
  blocked: BlockedInfo | null;
  outputs: Record<string, unknown> | null;
  genUiTrees: GenUiTreeV1[];
  errors: string[];
  start: (promptId: string, surface?: OverlaySurface) => void;
  setNode: (promptId: string, nodeId: string, patch: Partial<NodeRunState>) => void;
  touchNodeAsset: (promptId: string, nodeId: string) => void;
  appendAssetHistory: (promptId: string, nodeId: string, snapshot: AssetHistorySnapshot) => void;
  setBlocked: (promptId: string, info: BlockedInfo | null) => void;
  addGenUiTree: (promptId: string, tree: GenUiTreeV1) => void;
  finish: (
    promptId: string,
    result?: { outputs?: Record<string, unknown>; errors?: string[] },
  ) => void;
  reset: (promptId?: string) => void;
  getOverlay: (promptId: string) => PromptOverlayState | undefined;
}

/**
 * Holds live execution overlays keyed by `promptId`. Fed by the workflow
 * execution WebSocket (`/ws/executions/{prompt_id}`).
 */
export const useExecutionOverlay = create<ExecutionOverlayState>((set, get) => ({
  overlays: {},
  editorActivePromptId: null,
  activePromptId: null,
  promptId: null,
  running: false,
  nodes: {},
  assetHistory: [],
  assetOrder: [],
  blocked: null,
  outputs: null,
  genUiTrees: [],
  errors: [],

  getOverlay: (promptId) => get().overlays[promptId],

  start: (promptId, surface = 'editor') =>
    set((state) => {
      const overlays = {
        ...state.overlays,
        [promptId]: {
          ...emptyOverlay(),
          running: true,
        },
      };
      if (surface === 'chat') {
        return { overlays };
      }
      return withEditorSync(overlays, promptId);
    }),

  setNode: (promptId, nodeId, patch) =>
    set((state) => {
      const prev = state.overlays[promptId] ?? emptyOverlay();
      const existing: NodeRunState = prev.nodes[nodeId] ?? { status: 'pending' };
      const safePatch = cloneNodePatch(patch);
      const nextNode: NodeRunState = { ...existing, ...safePatch };
      const overlays: Record<string, PromptOverlayState> = {
        ...state.overlays,
        [promptId]: {
          ...prev,
          nodes: {
            ...prev.nodes,
            [nodeId]: nextNode,
          },
        },
      };
      return withEditorSync(overlays, state.editorActivePromptId);
    }),

  touchNodeAsset: (promptId, nodeId) =>
    set((state) => {
      const prev = state.overlays[promptId] ?? emptyOverlay();
      const assetOrder = [...prev.assetOrder.filter((id) => id !== nodeId), nodeId];
      const overlays = {
        ...state.overlays,
        [promptId]: { ...prev, assetOrder },
      };
      return withEditorSync(overlays, state.editorActivePromptId);
    }),

  appendAssetHistory: (promptId, nodeId, snapshot) =>
    set((state) => {
      const prev = state.overlays[promptId] ?? emptyOverlay();
      const assetHistory = appendAssetHistoryEntry(prev.assetHistory, nodeId, snapshot);
      if (assetHistory.length === prev.assetHistory.length) {
        return state;
      }
      const assetOrder = [...prev.assetOrder.filter((id) => id !== nodeId), nodeId];
      const overlays = {
        ...state.overlays,
        [promptId]: { ...prev, assetHistory, assetOrder },
      };
      return withEditorSync(overlays, state.editorActivePromptId);
    }),

  setBlocked: (promptId, info) =>
    set((state) => {
      const prev = state.overlays[promptId] ?? emptyOverlay();
      const overlays = {
        ...state.overlays,
        [promptId]: { ...prev, blocked: info },
      };
      return withEditorSync(overlays, state.editorActivePromptId);
    }),

  addGenUiTree: (promptId, tree) =>
    set((state) => {
      const prev = state.overlays[promptId] ?? emptyOverlay();
      const cloned = structuredClone(tree);
      const overlays = {
        ...state.overlays,
        [promptId]: { ...prev, genUiTrees: [...prev.genUiTrees, cloned] },
      };
      return withEditorSync(overlays, state.editorActivePromptId);
    }),

  finish: (promptId, result) =>
    set((state) => {
      const prev = state.overlays[promptId] ?? emptyOverlay();
      if (!prev.running && !result?.errors?.length) {
        return state;
      }
      const overlays = {
        ...state.overlays,
        [promptId]: {
          ...prev,
          running: false,
          outputs: result?.outputs ?? prev.outputs,
          errors: result?.errors ?? prev.errors,
        },
      };
      return withEditorSync(overlays, state.editorActivePromptId);
    }),

  reset: (promptId) =>
    set((state) => {
      if (!promptId) {
        return withEditorSync({}, null);
      }
      const overlays = { ...state.overlays };
      delete overlays[promptId];
      const editorActivePromptId =
        state.editorActivePromptId === promptId
          ? Object.keys(overlays)[0] ?? null
          : state.editorActivePromptId;
      return withEditorSync(overlays, editorActivePromptId);
    }),
}));
export type { AssetHistoryEntry, AssetHistorySnapshot } from './assetHistory';
export { assetVersionCount } from './assetHistory';
