import { useEffect, useState } from 'react';
import { resolveEffectiveMime } from '@/lib/mimeForPreview';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export type ChatFileBlobUrlState = {
  blobUrl: string | null;
  /** True while ``fileId`` is set and the preview request has not finished (success or terminal failure). */
  isLoading: boolean;
  /** True after a non-OK response or network failure (``blobUrl`` stays null). */
  isError: boolean;
};

const IDLE: ChatFileBlobUrlState = { blobUrl: null, isLoading: false, isError: false };

async function previewResponseToObjectUrl(
  res: Response,
  hintFilename?: string,
): Promise<string> {
  const headerType = res.headers
    .get('Content-Type')
    ?.split(';')[0]
    ?.trim()
    .toLowerCase();
  const buf = await res.arrayBuffer();
  const effectiveMime = resolveEffectiveMime(null, hintFilename ?? '');
  const useType =
    headerType && headerType !== 'application/octet-stream'
      ? headerType
      : effectiveMime.startsWith('image/')
        ? effectiveMime
        : 'image/png';
  return URL.createObjectURL(new Blob([buf], { type: useType }));
}

/**
 * Fetches ``GET /files/:id/preview`` with auth for inline chat/media previews.
 * Unlike pet preview hooks, does not filter by image MIME — supports previewable types the API serves.
 */
export function useChatFileBlobUrl(
  fileId: string | null,
  hintFilename?: string,
): ChatFileBlobUrlState {
  const [state, setState] = useState<ChatFileBlobUrlState>(IDLE);

  useEffect(() => {
    if (!fileId) {
      setState(IDLE);
      return;
    }
    setState({ blobUrl: null, isLoading: true, isError: false });
    const token =
      typeof localStorage !== 'undefined' ? localStorage.getItem('leagent-token') : null;
    let revoked: string | null = null;
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch(`${API_BASE}/files/${fileId}/preview`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          credentials: 'include',
        });
        if (cancelled) return;
        if (!res.ok) {
          setState({ blobUrl: null, isLoading: false, isError: true });
          return;
        }
        const u = await previewResponseToObjectUrl(res, hintFilename);
        if (cancelled) {
          URL.revokeObjectURL(u);
          return;
        }
        revoked = u;
        setState({ blobUrl: u, isLoading: false, isError: false });
      } catch {
        if (!cancelled) setState({ blobUrl: null, isLoading: false, isError: true });
      }
    })();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [fileId, hintFilename]);

  return state;
}
