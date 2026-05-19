import { useEffect, useState } from 'react';
import { effectivePetImageMime } from '@/lib/petAppearanceMime';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

/**
 * One-shot fetch of the same preview blob the hook uses (for callers that must not rely on a possibly stale object URL).
 */
export async function fetchAuthedFilePreviewBlob(
  fileId: string,
  mime: string | null | undefined,
  hintFilename?: string | null,
): Promise<Blob> {
  const effective = effectivePetImageMime(mime, hintFilename);
  if (!effective) {
    throw new Error('Unsupported or unknown image type for preview');
  }
  const token = typeof localStorage !== 'undefined' ? localStorage.getItem('leagent-token') : null;
  const res = await fetch(`${API_BASE}/files/${fileId}/preview`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: 'include',
  });
  if (!res.ok) {
    throw new Error(`Preview request failed: ${res.status}`);
  }
  return res.blob();
}

export type AuthedFileBlobUrlState = {
  url: string | null;
  /** True while a valid file preview request is in flight (success or terminal failure clears this). */
  isPending: boolean;
};

/**
 * Fetches an authenticated file preview and exposes an object URL (revoked on unmount).
 */
export function useAuthedFileBlobUrl(
  fileId: string | null,
  mime: string | null | undefined,
  hintFilename?: string | null,
): AuthedFileBlobUrlState {
  const [url, setUrl] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);

  useEffect(() => {
    const effective = effectivePetImageMime(mime, hintFilename);
    if (!fileId || !effective) {
      setUrl(null);
      setIsPending(false);
      return;
    }
    setUrl(null);
    setIsPending(true);
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
          setUrl(null);
          setIsPending(false);
          return;
        }
        const blob = await res.blob();
        if (cancelled) return;
        const u = URL.createObjectURL(blob);
        revoked = u;
        setUrl(u);
        setIsPending(false);
      } catch {
        if (!cancelled) {
          setUrl(null);
          setIsPending(false);
        }
      }
    })();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [fileId, mime, hintFilename]);

  return { url, isPending };
}
