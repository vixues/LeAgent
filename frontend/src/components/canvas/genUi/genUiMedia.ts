import type { GenUiNode, GenUiTreeV1 } from '@/types/genUi';

export type GenUiMediaKind = 'Image' | 'Video' | 'Model3D';

export interface GenUiMediaItem {
  kind: GenUiMediaKind;
  src: string;
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
  out.push({
    kind,
    src,
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
