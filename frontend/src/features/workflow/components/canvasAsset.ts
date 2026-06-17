import type { Node } from '@xyflow/react';

import { apiClient } from '@/api/client';
import type { GenUiMediaItem } from '@/components/canvas/genUi/genUiMedia';

/** Canvas-dropped input source kinds (ComfyUI LoadImage / note-style). */
export type CanvasAssetKind = 'image' | 'text' | 'file' | 'mesh3d';

export interface CanvasAssetNodeData extends Record<string, unknown> {
  assetKind: CanvasAssetKind;
  fileId?: string;
  fileName?: string;
  mimeType?: string;
  previewUrl?: string;
  textContent?: string;
  label?: string;
  /** Natural pixel size — used to size the node frame to the image aspect ratio. */
  imageWidth?: number;
  imageHeight?: number;
}

export const CANVAS_ASSET_NODE_TYPE = 'canvas-asset';

export const DEFAULT_ASSET_WIDTH = 220;
export const DEFAULT_ASSET_HEIGHT = 160;
export const DEFAULT_TEXT_ASSET_WIDTH = 200;
export const DEFAULT_TEXT_ASSET_HEIGHT = 120;
export const IMAGE_NODE_MAX_EDGE = 480;
export const IMAGE_NODE_MIN_EDGE = 48;

export function isCanvasAssetNode(
  node: Node | undefined | null,
): node is Node<CanvasAssetNodeData> {
  return node?.type === CANVAS_ASSET_NODE_TYPE;
}

export const DEFAULT_MESH_ASSET_WIDTH = 260;
export const DEFAULT_MESH_ASSET_HEIGHT = 300;
export const MESH_ASSET_HEADER_HEIGHT = 36;
export const MESH_ASSET_PREVIEW_HEIGHT = DEFAULT_MESH_ASSET_HEIGHT - MESH_ASSET_HEADER_HEIGHT;

export function isMesh3dFile(file: File): boolean {
  if (/\.(glb|gltf|obj|fbx)$/i.test(file.name)) return true;
  const mime = (file.type || '').toLowerCase();
  return mime.includes('gltf') || mime === 'model/gltf-binary';
}

export function classifyDroppedFile(file: File): CanvasAssetKind {
  if (file.type.startsWith('image/')) return 'image';
  if (isMesh3dFile(file)) return 'mesh3d';
  if (file.type.startsWith('text/') || /\.(txt|md|json|yaml|yml|csv)$/i.test(file.name)) {
    return 'text';
  }
  return 'file';
}

export async function uploadWorkflowAsset(file: File): Promise<{
  id: string;
  filename: string;
  mime_type?: string;
  preview_url?: string;
}> {
  const fd = new FormData();
  fd.append('file', file);
  const res = await apiClient.upload<{
    id: string;
    filename: string;
    mime_type?: string;
  }>('/workflow/assets/upload', fd);
  const id = String(res?.id || '').trim();
  if (!id) throw new Error('Upload failed');
  return {
    id,
    filename: res.filename || file.name,
    mime_type: res.mime_type || file.type,
    preview_url: `/api/v1/files/${id}/preview`,
  };
}

export async function readFileAsText(file: File, maxChars = 32_000): Promise<string> {
  const text = await file.text();
  return text.length > maxChars ? `${text.slice(0, maxChars)}\n…` : text;
}

/** Read intrinsic pixel dimensions from a local image file. */
export async function measureImageFile(file: File): Promise<{ width: number; height: number }> {
  if (typeof createImageBitmap === 'function') {
    const bitmap = await createImageBitmap(file);
    const size = { width: bitmap.width, height: bitmap.height };
    bitmap.close();
    return size;
  }
  const url = URL.createObjectURL(file);
  try {
    return await new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
      img.onerror = () => reject(new Error('Failed to decode image'));
      img.src = url;
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Scale image dimensions to fit on canvas while preserving aspect ratio. */
export function fitImageDisplaySize(
  naturalWidth: number,
  naturalHeight: number,
  maxEdge = IMAGE_NODE_MAX_EDGE,
): { width: number; height: number } {
  if (naturalWidth <= 0 || naturalHeight <= 0) {
    return { width: DEFAULT_ASSET_WIDTH, height: DEFAULT_ASSET_HEIGHT };
  }
  const scale = Math.min(1, maxEdge / Math.max(naturalWidth, naturalHeight));
  return {
    width: Math.max(IMAGE_NODE_MIN_EDGE, Math.round(naturalWidth * scale)),
    height: Math.max(IMAGE_NODE_MIN_EDGE, Math.round(naturalHeight * scale)),
  };
}

function resolveImageNodeSize(
  payload: CanvasAssetNodeData,
  size?: { width: number; height: number },
): { width: number; height: number } | undefined {
  if (size) return size;
  if (
    payload.assetKind === 'image' &&
    typeof payload.imageWidth === 'number' &&
    typeof payload.imageHeight === 'number'
  ) {
    return fitImageDisplaySize(payload.imageWidth, payload.imageHeight);
  }
  if (payload.assetKind === 'file' && payload.mimeType?.startsWith('image/')) {
    if (typeof payload.imageWidth === 'number' && typeof payload.imageHeight === 'number') {
      return fitImageDisplaySize(payload.imageWidth, payload.imageHeight);
    }
  }
  return undefined;
}

/** Output socket id on canvas asset nodes (matches serialized backend node). */
export function canvasAssetSourceHandle(kind: CanvasAssetKind): string {
  if (kind === 'image') return 'image';
  if (kind === 'mesh3d') return 'mesh';
  return 'result';
}

/** Wire type emitted by a canvas asset output handle. */
export function canvasAssetOutputWireType(kind: CanvasAssetKind, handle?: string | null): string {
  if (kind === 'image' && (handle === 'image' || !handle)) return 'IMAGE';
  if (kind === 'mesh3d' && (handle === 'mesh' || !handle)) return 'MESH3D';
  if (kind === 'text') return 'STRING';
  return 'OBJECT';
}

export function canvasAssetPreview(data: CanvasAssetNodeData): GenUiMediaItem | null {
  if (data.assetKind === 'text') return null;
  const src = data.previewUrl || (data.fileId ? `/api/v1/files/${data.fileId}/preview` : '');
  if (!src) return null;
  if (data.assetKind === 'mesh3d' || /\.(glb|gltf)$/i.test(data.fileName || '')) {
    return { kind: 'Model3D', src, caption: data.fileName || data.label };
  }
  if (data.assetKind === 'image' || data.mimeType?.startsWith('image/')) {
    return { kind: 'Image', src, caption: data.fileName || data.label };
  }
  return null;
}

export function canvasAssetLabel(data: CanvasAssetNodeData): string {
  if (data.label) return data.label;
  if (data.assetKind === 'text') {
    const t = (data.textContent || '').trim();
    return t.length > 24 ? `${t.slice(0, 24)}…` : t || 'Text';
  }
  return data.fileName || 'File';
}

export function buildCanvasAssetNode(
  id: string,
  position: { x: number; y: number },
  payload: CanvasAssetNodeData,
  size?: { width: number; height: number },
): Node<CanvasAssetNodeData> {
  const isText = payload.assetKind === 'text';
  const isImage =
    payload.assetKind === 'image' || payload.mimeType?.startsWith('image/');
  const isMesh = payload.assetKind === 'mesh3d';
  const imageSize = isImage ? resolveImageNodeSize(payload, size) : undefined;
  const width =
    imageSize?.width ??
    size?.width ??
    (isText ? DEFAULT_TEXT_ASSET_WIDTH : isMesh ? DEFAULT_MESH_ASSET_WIDTH : DEFAULT_ASSET_WIDTH);
  const height =
    imageSize?.height ??
    size?.height ??
    (isText ? DEFAULT_TEXT_ASSET_HEIGHT : isMesh ? DEFAULT_MESH_ASSET_HEIGHT : DEFAULT_ASSET_HEIGHT);
  return {
    id,
    type: CANVAS_ASSET_NODE_TYPE,
    position,
    data: {
      ...payload,
      label: payload.label || canvasAssetLabel(payload),
    },
    style: { width, height },
    draggable: true,
    selectable: true,
  };
}
