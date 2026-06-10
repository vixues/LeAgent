import { create } from 'zustand';
import type { GenUiTreeV1, UiPatchStreamPayload, UiTreeStreamPayload } from '@/types/genUi';
import type { Message } from '@/types/chat';

function treeKey(sessionId: string, messageId: string): string {
  return `${sessionId}::${messageId}`;
}

/** Decode one RFC-6901 JSON Pointer token. */
function decodePointerToken(token: string): string {
  return token.replace(/~1/g, '/').replace(/~0/g, '~');
}

/**
 * Apply RFC-6902 `add` / `replace` / `remove` patches to a GenUi tree
 * document (matching the backend `UI_PATCH_SCHEMA` contract). Invalid
 * patches are skipped; the document is cloned before mutation.
 */
export function applyJsonPatches(
  doc: GenUiTreeV1,
  patches: UiPatchStreamPayload['patches'],
): GenUiTreeV1 {
  const next = structuredClone(doc) as unknown as Record<string, unknown>;
  for (const p of patches) {
    if (!p || typeof p.path !== 'string' || !p.path.startsWith('/')) continue;
    const tokens = p.path.slice(1).split('/').map(decodePointerToken);
    if (tokens.length === 0) continue;
    applyOnePatch(next, tokens, p.op, p.value);
  }
  return next as unknown as GenUiTreeV1;
}

function applyOnePatch(
  doc: Record<string, unknown>,
  tokens: string[],
  op: 'add' | 'replace' | 'remove',
  value: unknown,
): void {
  // Walk to the parent of the target.
  let parent: unknown = doc;
  for (let i = 0; i < tokens.length - 1; i += 1) {
    const tok = tokens[i]!;
    if (Array.isArray(parent)) {
      const idx = Number(tok);
      if (!Number.isInteger(idx) || idx < 0 || idx >= parent.length) return;
      parent = parent[idx];
    } else if (parent && typeof parent === 'object') {
      parent = (parent as Record<string, unknown>)[tok];
    } else {
      return;
    }
  }
  if (parent == null || typeof parent !== 'object') return;

  const last = tokens[tokens.length - 1]!;
  if (Array.isArray(parent)) {
    const arr = parent as unknown[];
    if (op === 'add') {
      if (last === '-') {
        arr.push(value);
        return;
      }
      const idx = Number(last);
      if (!Number.isInteger(idx) || idx < 0 || idx > arr.length) return;
      arr.splice(idx, 0, value);
      return;
    }
    const idx = Number(last);
    if (!Number.isInteger(idx) || idx < 0 || idx >= arr.length) return;
    if (op === 'replace') arr[idx] = value;
    else arr.splice(idx, 1);
    return;
  }

  const obj = parent as Record<string, unknown>;
  if (op === 'remove') {
    delete obj[last];
    return;
  }
  // `add` and `replace` both assign for objects (RFC 6902 §4.1/4.3 —
  // replace requires existence, but we stay lenient for streaming patches).
  obj[last] = value;
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
    const next = applyJsonPatches(current, payload.patches);
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
