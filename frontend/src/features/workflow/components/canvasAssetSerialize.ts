import type { EditorNode } from '../graph/serialization';
import {
  type CanvasAssetKind,
  type CanvasAssetNodeData,
  CANVAS_ASSET_NODE_TYPE,
  buildCanvasAssetNode,
} from './canvasAsset';

interface EditorAssetMeta {
  editorAsset?: CanvasAssetNodeData & { width?: number; height?: number };
}

function parseEditorAssetMeta(meta: Record<string, unknown> | undefined): CanvasAssetNodeData | null {
  if (!meta || typeof meta !== 'object') return null;
  const raw = (meta as EditorAssetMeta).editorAsset;
  if (!raw || typeof raw !== 'object') return null;
  const kind = raw.assetKind;
  if (kind !== 'image' && kind !== 'text' && kind !== 'file' && kind !== 'mesh3d') return null;
  return raw as CanvasAssetNodeData;
}

/** Map a canvas asset editor node to an executable canonical node spec (same id). */
export function canvasAssetToCanonical(
  node: EditorNode,
): { class_type: string; inputs: Record<string, unknown>; meta: Record<string, unknown> } | null {
  if (node.type !== CANVAS_ASSET_NODE_TYPE) return null;
  const data = node.data as CanvasAssetNodeData;
  const width = typeof node.style?.width === 'number' ? node.style.width : undefined;
  const height = typeof node.style?.height === 'number' ? node.style.height : undefined;
  const editorAsset = { ...data, width, height };
  const position = {
    x: Math.round(node.position.x),
    y: Math.round(node.position.y),
  };

  if (data.assetKind === 'mesh3d') {
    return {
      class_type: 'LoadMesh3D',
      inputs: { file: data.fileId ?? '' },
      meta: {
        position,
        title: data.label,
        editorAsset,
      },
    };
  }

  if (data.assetKind === 'image' || (data.assetKind === 'file' && data.mimeType?.startsWith('image/'))) {
    return {
      class_type: 'LoadImage',
      inputs: { file: data.fileId ?? '' },
      meta: {
        position,
        title: data.label,
        editorAsset,
      },
    };
  }

  if (data.assetKind === 'text') {
    const text = data.textContent ?? '';
    return {
      class_type: 'ScriptNode',
      inputs: {
        source: 'result = str(text)\n',
        inputs: { text },
        timeout_sec: 3.0,
      },
      meta: {
        position,
        title: data.label || 'Text',
        editorAsset,
      },
    };
  }

  const fileId = data.fileId ?? '';
  return {
    class_type: 'ScriptNode',
    inputs: {
      source: [
        'result = {',
        '    "file_id": str(file_id),',
        '    "preview_url": "/api/v1/files/" + str(file_id) + "/preview",',
        '    "filename": str(filename),',
        '}',
      ].join('\n'),
      inputs: { file_id: fileId, filename: data.fileName ?? fileId },
      timeout_sec: 3.0,
    },
    meta: {
      position,
      title: data.fileName || 'File',
      editorAsset,
    },
  };
}

/** Rebuild a canvas-asset editor node from a stored canonical spec, if tagged. */
export function canonicalToCanvasAsset(
  id: string,
  spec: { class_type: string; inputs?: Record<string, unknown>; meta?: Record<string, unknown> },
): EditorNode | null {
  const asset = parseEditorAssetMeta(spec.meta as Record<string, unknown> | undefined);
  if (!asset) {
    if (spec.class_type === 'LoadImage') {
      const file = spec.inputs?.file;
      if (typeof file !== 'string' || !file) return null;
      return buildCanvasAssetNode(
        id,
        spec.meta?.position as { x: number; y: number } ?? { x: 0, y: 0 },
        {
          assetKind: 'image',
          fileId: file,
          previewUrl: `/api/v1/files/${file}/preview`,
          label: typeof spec.meta?.title === 'string' ? spec.meta.title : undefined,
        },
      ) as EditorNode;
    }
    if (spec.class_type === 'LoadMesh3D') {
      const file = spec.inputs?.file;
      if (typeof file !== 'string' || !file) return null;
      return buildCanvasAssetNode(
        id,
        spec.meta?.position as { x: number; y: number } ?? { x: 0, y: 0 },
        {
          assetKind: 'mesh3d',
          fileId: file,
          previewUrl: `/api/v1/files/${file}/preview`,
          label: typeof spec.meta?.title === 'string' ? spec.meta.title : undefined,
        },
      ) as EditorNode;
    }
    return null;
  }

  const pos =
    spec.meta?.position && typeof spec.meta.position === 'object'
      ? (spec.meta.position as { x: number; y: number })
      : { x: 0, y: 0 };
  const w = typeof asset.width === 'number' ? asset.width : undefined;
  const h = typeof asset.height === 'number' ? asset.height : undefined;
  return buildCanvasAssetNode(
    id,
    pos,
    asset,
    w && h ? { width: w, height: h } : undefined,
  ) as EditorNode;
}

export function isCanvasAssetCanonical(
  spec: { class_type: string; meta?: Record<string, unknown> },
): boolean {
  return parseEditorAssetMeta(spec.meta) !== null || spec.class_type === 'LoadImage' || spec.class_type === 'LoadMesh3D';
}

export function canvasAssetKindFromCanonical(
  spec: { class_type: string; meta?: Record<string, unknown> },
): CanvasAssetKind {
  const asset = parseEditorAssetMeta(spec.meta);
  if (asset) return asset.assetKind;
  if (spec.class_type === 'LoadImage') return 'image';
  if (spec.class_type === 'LoadMesh3D') return 'mesh3d';
  return 'file';
}
