import { useEffect, useRef, useState } from 'react';
import { getAccessToken } from '@/api/client';
import { pdfjsLib, type PdfDocument } from './pdfjs';

interface UsePdfDocumentResult {
  doc: PdfDocument | null;
  numPages: number;
  loading: boolean;
  error: string | null;
}

/**
 * Loads a PDF document by file id. The bytes are fetched with credentials so
 * the authenticated `/preview` endpoint works (a plain URL handed to pdf.js
 * could not send the auth cookie reliably across origins / proxies).
 */
export function usePdfDocument(fileId: string | null): UsePdfDocumentResult {
  const [doc, setDoc] = useState<PdfDocument | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const docRef = useRef<PdfDocument | null>(null);

  useEffect(() => {
    if (!fileId) {
      setDoc(null);
      setNumPages(0);
      return;
    }

    let cancelled = false;
    const previewUrl = `/api/v1/files/${fileId}/preview`;
    setLoading(true);
    setError(null);

    const run = async () => {
      try {
        const token = getAccessToken();
        const res = await fetch(previewUrl, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          credentials: 'include',
        });
        if (!res.ok) throw new Error(`Preview request failed (${res.status})`);
        const data = await res.arrayBuffer();
        if (cancelled) return;
        const loadingTask = pdfjsLib.getDocument({ data });
        const loaded = await loadingTask.promise;
        if (cancelled) {
          void loaded.destroy();
          return;
        }
        docRef.current = loaded;
        setDoc(loaded);
        setNumPages(loaded.numPages);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load PDF');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void run();

    return () => {
      cancelled = true;
      if (docRef.current) {
        void docRef.current.destroy();
        docRef.current = null;
      }
    };
  }, [fileId]);

  return { doc, numPages, loading, error };
}
