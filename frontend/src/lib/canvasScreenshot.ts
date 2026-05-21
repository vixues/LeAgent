import { apiClient } from '@/api/client';
import { resolveCanvasPreviewUrl } from '@/lib/previewUrl';
import type { SessionCanvasArtifactDTO } from '@/stores/artifact';

/** Extract signed preview token from a canvas preview path or absolute URL. */
export function extractCanvasPreviewToken(previewPathOrUrl: string): string | null {
  if (!previewPathOrUrl.trim()) return null;
  try {
    const url = previewPathOrUrl.startsWith('http://') || previewPathOrUrl.startsWith('https://')
      ? new URL(previewPathOrUrl)
      : new URL(previewPathOrUrl, 'http://local.invalid');
    if (!url.pathname.includes('/canvas/preview')) return null;
    const token = url.searchParams.get('token');
    return token && token.length >= 10 ? token : null;
  } catch {
    return null;
  }
}

/** Mint a fresh preview token via session canvas list (same source as history hydrate). */
export async function refreshCanvasPreviewToken(
  sessionId: string,
  canvasId: string,
): Promise<string | null> {
  try {
    const items = await apiClient.get<SessionCanvasArtifactDTO[]>(
      `/canvas/by-session/${sessionId}`,
    );
    const match = items.find((a) => a.canvas_id === canvasId);
    if (!match?.preview_path) return null;
    return extractCanvasPreviewToken(resolveCanvasPreviewUrl(match.preview_path));
  } catch {
    return null;
  }
}

export async function fetchCanvasPreviewScreenshot(
  token: string,
  options?: { width?: number; height?: number; format?: 'png' | 'jpeg' },
): Promise<Blob> {
  const params = new URLSearchParams({
    token,
    format: options?.format ?? 'png',
    width: String(options?.width ?? 1200),
    height: String(options?.height ?? 800),
  });
  const res = await fetch(`/api/v1/canvas/preview/screenshot?${params}`);
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      if (body && typeof body === 'object' && 'detail' in body) {
        detail = String((body as { detail: unknown }).detail);
      }
    } catch {
      detail = await res.text().catch(() => '');
    }
    throw new Error(detail || `Screenshot failed (${res.status})`);
  }
  const blob = await res.blob();
  if (!blob.type.startsWith('image/') || blob.size < 64) {
    throw new Error('Invalid screenshot response');
  }
  return blob;
}

export function downloadImageBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
