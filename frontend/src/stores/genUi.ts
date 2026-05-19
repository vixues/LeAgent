import { create } from 'zustand';
import type { GenUiTreeV1, UiPatchStreamPayload, UiTreeStreamPayload } from '@/types/genUi';
import type { Message } from '@/types/chat';

function treeKey(sessionId: string, messageId: string): string {
  return `${sessionId}::${messageId}`;
}

interface GenUiState {
  /** Full trees keyed by `sessionId::messageId`. */
  trees: Record<string, GenUiTreeV1 | null>;
  /** Last `emit_ui_tree` tool_call_id that updated the tree for a message (companion SSE). */
  sourceToolCallByMessage: Record<string, string>;
  /** Message keys whose last tree emission failed — patches are rejected until a fresh full tree arrives. */
  errorTrees: Set<string>;
  setFromStream: (sessionId: string, messageId: string, payload: UiTreeStreamPayload) => void;
  applyPatch: (sessionId: string, messageId: string, payload: UiPatchStreamPayload) => void;
  /** Mark a tree as errored so subsequent patches are rejected. */
  markError: (sessionId: string, messageId: string) => void;
  /** After `/chat/stream` persists rows, client temp ids become server UUIDs. */
  remapMessageId: (sessionId: string, oldMessageId: string, newMessageId: string) => void;
  clearForSession: (sessionId: string) => void;
}

/**
 * In-memory generative UI state for the active stream (rehydration from
 * server message extensions can be added later).
 */
export const useGenUiStore = create<GenUiState>()((set, get) => ({
  trees: {},
  sourceToolCallByMessage: {},
  errorTrees: new Set<string>(),

  setFromStream(sessionId, messageId, payload) {
    const k = treeKey(sessionId, messageId);
    const tree = payload.tree;
    if (!tree || (tree as { schemaVersion?: string }).schemaVersion !== '1' || !('root' in tree)) return;
    const tid =
      typeof payload.tool_call_id === 'string' && payload.tool_call_id.length > 0
        ? payload.tool_call_id
        : undefined;
    set((s) => {
      const nextErrors = new Set(s.errorTrees);
      nextErrors.delete(k);
      return {
        trees: { ...s.trees, [k]: tree as GenUiTreeV1 },
        sourceToolCallByMessage:
          tid != null
            ? { ...s.sourceToolCallByMessage, [k]: tid }
            : s.sourceToolCallByMessage,
        errorTrees: nextErrors,
      };
    });
  },

  applyPatch(sessionId, messageId, payload) {
    const k = treeKey(sessionId, messageId);
    if (get().errorTrees.has(k)) return;
    const current = get().trees[k];
    if (!current) return;
    const next = { ...current, root: structuredClone(current.root) };
    for (const p of payload.patches) {
      if (p.op === 'replace' && p.path === '/root' && p.value && typeof p.value === 'object') {
        next.root = p.value as GenUiTreeV1['root'];
      }
    }
    set((s) => ({ trees: { ...s.trees, [k]: next } }));
  },

  markError(sessionId, messageId) {
    const k = treeKey(sessionId, messageId);
    set((s) => {
      const nextErrors = new Set(s.errorTrees);
      nextErrors.add(k);
      return { errorTrees: nextErrors };
    });
  },

  remapMessageId(sessionId, oldMessageId, newMessageId) {
    if (oldMessageId === newMessageId) return;
    const oldK = treeKey(sessionId, oldMessageId);
    const newK = treeKey(sessionId, newMessageId);
    set((s) => {
      const trees = { ...s.trees };
      if (oldK in trees) {
        trees[newK] = trees[oldK] ?? null;
        delete trees[oldK];
      }
      const sourceToolCallByMessage = { ...s.sourceToolCallByMessage };
      if (oldK in sourceToolCallByMessage) {
        const sourceToolCallId = sourceToolCallByMessage[oldK];
        if (sourceToolCallId) {
          sourceToolCallByMessage[newK] = sourceToolCallId;
        }
        delete sourceToolCallByMessage[oldK];
      }
      const nextErrors = new Set(s.errorTrees);
      if (nextErrors.has(oldK)) {
        nextErrors.delete(oldK);
        nextErrors.add(newK);
      }
      return { trees, sourceToolCallByMessage, errorTrees: nextErrors };
    });
  },

  clearForSession(sessionId) {
    set((s) => {
      const next: Record<string, GenUiTreeV1 | null> = { ...s.trees };
      const src: Record<string, string> = { ...s.sourceToolCallByMessage };
      const nextErrors = new Set(s.errorTrees);
      for (const key of Object.keys(next)) {
        if (key.startsWith(`${sessionId}::`)) {
          delete next[key];
          delete src[key];
          nextErrors.delete(key);
        }
      }
      return { trees: next, sourceToolCallByMessage: src, errorTrees: nextErrors };
    });
  },
}));

export { treeKey as genUiTreeKey };

/** Replay ``Message.genUiReplay`` into the store after GET /messages (history). */
export function hydrateGenUiFromMessages(sessionId: string, messages: Message[]): void {
  const { setFromStream } = useGenUiStore.getState();
  for (const m of messages) {
    const r = m.genUiReplay;
    if (!r?.tree || typeof r.tree !== 'object') continue;
    setFromStream(sessionId, m.id, {
      tree: r.tree,
      canvas_id: r.canvas_id,
      tool_call_id: r.tool_call_id,
    });
  }
}
