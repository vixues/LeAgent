import { useEffect, useState } from 'react';

export type CanvasPreviewDocState = {
  /** Fetched HTML suitable for iframe ``srcDoc`` (API canvas preview). */
  srcDoc: string | null;
  isLoading: boolean;
  isError: boolean;
};

const IDLE: CanvasPreviewDocState = {
  srcDoc: null,
  isLoading: false,
  isError: false,
};

/**
 * Load hosted ``/api/v1/canvas/preview`` HTML for ``srcDoc`` rendering.
 * Embedded browsers (e.g. Cursor Simple Browser) often block sandboxed ``src``
 * navigations that work in standalone Chrome; fetching + ``srcDoc`` is reliable.
 */
export function useCanvasPreviewDoc(
  previewUrl: string,
  enabled: boolean,
): CanvasPreviewDocState {
  const [state, setState] = useState<CanvasPreviewDocState>(IDLE);

  useEffect(() => {
    if (!enabled || !previewUrl.trim()) {
      setState(IDLE);
      return;
    }

    let cancelled = false;
    setState({ srcDoc: null, isLoading: true, isError: false });

    void (async () => {
      try {
        const res = await fetch(previewUrl, { credentials: 'include' });
        if (!res.ok) throw new Error(`preview ${res.status}`);
        const html = await res.text();
        if (cancelled) return;
        setState({ srcDoc: html, isLoading: false, isError: false });
      } catch {
        if (!cancelled) {
          setState({ srcDoc: null, isLoading: false, isError: true });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [previewUrl, enabled]);

  return state;
}
