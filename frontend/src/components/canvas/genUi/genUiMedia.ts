import type { GenUiNode, GenUiTreeV1 } from '@/types/genUi';

import type { AssetHistoryEntry } from '@/features/workflow/store/assetHistory';

export type GenUiMediaKind = 'Image' | 'Video' | 'Model3D';

export interface GenUiMediaItem {
  kind: GenUiMediaKind;
  src: string;
  /** Managed file id when the GenUI node carries ``props.fileId``. */
  fileId?: string;
  caption?: string;
  poster?: string;
}

const MEDIA_KINDS = new Set<GenUiMediaKind>(['Image', 'Video', 'Model3D']);

function pushIfMedia(node: GenUiNode, out: GenUiMediaItem[]): void {
  const kind = node.kind as GenUiMediaKind;
  if (!MEDIA_KINDS.has(kind)) return;
  const p = (node.props || {}) as Record<string, unknown>;
  const src = typeof p.src === 'string' ? p.src : '';
  if (!src) return;
  const fileId = typeof p.fileId === 'string' && p.fileId.trim() ? p.fileId.trim() : undefined;
  out.push({
    kind,
    src,
    fileId,
    caption: typeof p.caption === 'string' ? p.caption : undefined,
    poster: typeof p.poster === 'string' ? p.poster : undefined,
  });
}

function walk(node: GenUiNode | undefined, out: GenUiMediaItem[]): void {
  if (!node) return;
  pushIfMedia(node, out);
  for (const child of node.children || []) walk(child, out);
}

/** Collect every Image/Video/Model3D leaf (with a src) from a GenUI tree. */
export function extractMediaItems(tree: GenUiTreeV1 | null | undefined): GenUiMediaItem[] {
  if (!tree?.root) return [];
  const out: GenUiMediaItem[] = [];
  walk(tree.root, out);
  return out;
}

/** First media item in a tree, if any (used for inline node thumbnails). */
export function firstMediaItem(tree: GenUiTreeV1 | null | undefined): GenUiMediaItem | null {
  return extractMediaItems(tree)[0] ?? null;
}

/** Resolve inline media from a node's execution overlay (gen_ui tree or metadata). */
export function mediaFromNodeRunState(state: {
  ui?: GenUiTreeV1 | null;
  metadata?: Record<string, unknown>;
} | null | undefined): GenUiMediaItem | null {
  if (!state) return null;
  const fromUi = firstMediaItem(state.ui ?? null);
  const md = state.metadata ?? {};
  const mdFileId = typeof md.file_id === 'string' ? md.file_id.trim() : '';
  const uiFileId = fromUi?.fileId?.trim() || '';
  const resolvedFileId = mdFileId || uiFileId;
  if (resolvedFileId) {
    const gk = typeof md.genui_kind === 'string' ? md.genui_kind : '';
    const kind: GenUiMediaKind =
      gk === 'Video' || gk === 'Model3D' ? gk : (fromUi?.kind ?? 'Image');
    return {
      kind,
      fileId: resolvedFileId,
      src: `/api/v1/files/${resolvedFileId}/preview`,
    };
  }
  if (fromUi?.src) return fromUi;
  const src =
    (typeof md.src === 'string' && md.src.trim()) ||
    (typeof md.preview_url === 'string' && md.preview_url.trim()) ||
    '';
  if (!src) return null;
  const gk = typeof md.genui_kind === 'string' ? md.genui_kind : '';
  const kind: GenUiMediaKind =
    gk === 'Video' || gk === 'Model3D' ? gk : 'Image';
  return { kind, src };
}

function walkPatchFileRef(
  node: GenUiNode | undefined,
  fileId: string,
  dimCaption: string | undefined,
): void {
  if (!node) return;
  if (MEDIA_KINDS.has(node.kind as GenUiMediaKind)) {
    const props = { ...((node.props || {}) as Record<string, unknown>) };
    props.fileId = fileId;
    props.src = `/api/v1/files/${fileId}/preview`;
    if (dimCaption) props.caption = dimCaption;
    node.props = props;
  }
  for (const child of node.children || []) walkPatchFileRef(child, fileId, dimCaption);
}

/** Align every media leaf in a GenUI tree with the canonical managed ``file_id``. */
export function patchAssetTreeFileRef(
  tree: GenUiTreeV1,
  fileId: string,
  dims?: { width?: unknown; height?: unknown },
): GenUiTreeV1 {
  const cloned = structuredClone(tree);
  const w = typeof dims?.width === 'number' ? dims.width : null;
  const h = typeof dims?.height === 'number' ? dims.height : null;
  const dimCaption = w && h ? `${w}\u00d7${h}` : undefined;
  walkPatchFileRef(cloned.root, fileId.trim(), dimCaption);
  return cloned;
}

export function nodeHasAsset(state: {
  ui?: GenUiTreeV1 | null;
  metadata?: Record<string, unknown>;
} | null | undefined): boolean {
  return mediaFromNodeRunState(state) != null;
}

/** Build a run-panel GenUI tree from the same resolver the canvas node card uses. */
export function buildAssetTreeFromRunState(
  nodeId: string,
  state: {
    ui?: GenUiTreeV1 | null;
    metadata?: Record<string, unknown>;
  },
  label?: string,
): GenUiTreeV1 | null {
  const media = mediaFromNodeRunState(state);
  if (!media?.src) return null;
  const md = state.metadata ?? {};
  const w = typeof md.width === 'number' ? md.width : null;
  const h = typeof md.height === 'number' ? md.height : null;
  const caption = media.caption || (w && h ? `${w}\u00d7${h}` : undefined);
  const title = label?.trim() || nodeId;
  return {
    schemaVersion: '1',
    root: {
      kind: 'Stack',
      children: [
        { kind: 'SectionHeader', props: { title } },
        {
          kind: media.kind,
          props: {
            src: media.src,
            fileId: media.fileId,
            caption,
            rounded: true,
            maxHeight: 320,
          },
        },
      ],
    },
  };
}

export function listOrderedNodeAssets(
  nodes: Record<string, { ui?: GenUiTreeV1 | null; metadata?: Record<string, unknown> }>,
  order: string[],
): Array<{ nodeId: string; tree: GenUiTreeV1 }> {
  const out: Array<{ nodeId: string; tree: GenUiTreeV1 }> = [];
  for (const nodeId of order) {
    const state = nodes[nodeId];
    if (!state) continue;
    const tree = buildAssetTreeFromRunState(nodeId, state);
    if (tree) out.push({ nodeId, tree });
  }
  return out;
}

function historyRefineIteration(entry: AssetHistoryEntry): number | null {
  const raw = entry.metadata?.refine_iteration ?? entry.metadata?.iteration;
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw;
  if (typeof raw === 'string' && raw.trim() !== '' && Number.isFinite(Number(raw))) {
    return Number(raw);
  }
  return null;
}

/** Human-readable label for one asset-history gallery row. */
export function formatAssetHistoryLabel(
  entry: AssetHistoryEntry,
  nodeLabel?: string,
  t?: (key: string, fallback: string, opts?: Record<string, unknown>) => string,
): string {
  const base = nodeLabel?.trim() || entry.nodeId;
  const refine = historyRefineIteration(entry);
  if (refine != null && refine > 0) {
    return t
      ? t('runPanel.assetRefine', '{{node}} · refine {{n}}', { node: base, n: refine })
      : `${base} · refine ${refine}`;
  }
  if (entry.nodeRunIndex > 1) {
    return t
      ? t('runPanel.assetVersion', '{{node}} · v{{n}}', { node: base, n: entry.nodeRunIndex })
      : `${base} · v${entry.nodeRunIndex}`;
  }
  return t
    ? t('runPanel.assetInitial', '{{node}} · initial', { node: base })
    : `${base} · initial`;
}

/** Chronological asset gallery (every unique file, including refine re-runs). */
export function listAssetHistoryTrees(
  history: AssetHistoryEntry[],
  nodeLabels?: Record<string, string>,
  t?: (key: string, fallback: string, opts?: Record<string, unknown>) => string,
): Array<{ id: string; nodeId: string; tree: GenUiTreeV1 }> {
  const out: Array<{ id: string; nodeId: string; tree: GenUiTreeV1 }> = [];
  for (const entry of history) {
    const label = formatAssetHistoryLabel(entry, nodeLabels?.[entry.nodeId], t);
    const tree = buildAssetTreeFromRunState(
      entry.nodeId,
      { ui: entry.ui, metadata: entry.metadata },
      label,
    );
    if (tree) out.push({ id: entry.id, nodeId: entry.nodeId, tree });
  }
  return out;
}
