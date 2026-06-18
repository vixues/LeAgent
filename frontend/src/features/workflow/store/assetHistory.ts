import type { GenUiTreeV1 } from '@/types/genUi';

/** One immutable asset snapshot from a node ``executed`` event (per unique file). */
export interface AssetHistoryEntry {
  /** Stable key ``{nodeId}:{fileId}``. */
  id: string;
  nodeId: string;
  fileId: string;
  /** 1-based run index for this node id within the prompt (supports refine re-runs). */
  nodeRunIndex: number;
  /** Monotonic append order across the whole execution. */
  sequence: number;
  ui?: GenUiTreeV1 | null;
  metadata?: Record<string, unknown>;
}

export interface AssetHistorySnapshot {
  ui?: GenUiTreeV1 | null;
  metadata?: Record<string, unknown>;
  fileId: string;
}

export function appendAssetHistoryEntry(
  prev: AssetHistoryEntry[],
  nodeId: string,
  snapshot: AssetHistorySnapshot,
): AssetHistoryEntry[] {
  const fileId = snapshot.fileId.trim();
  if (!fileId) return prev;
  if (prev.some((e) => e.fileId === fileId)) return prev;

  const nodeRunIndex = prev.filter((e) => e.nodeId === nodeId).length + 1;
  const entry: AssetHistoryEntry = {
    id: `${nodeId}:${fileId}`,
    nodeId,
    fileId,
    nodeRunIndex,
    sequence: prev.length,
    ui: snapshot.ui ? structuredClone(snapshot.ui) : undefined,
    metadata: snapshot.metadata ? structuredClone(snapshot.metadata) : undefined,
  };
  return [...prev, entry];
}

/** Count distinct file versions produced by a node during one run. */
export function assetVersionCount(history: AssetHistoryEntry[], nodeId: string): number {
  return history.filter((e) => e.nodeId === nodeId).length;
}
