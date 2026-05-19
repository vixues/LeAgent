import { getAccessToken } from '@/api/client';
import type { GenUiTreeV1 } from '@/types/genUi';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export interface ExportGenUiPdfOptions {
  sessionId: string;
  messageId?: string;
  tree: GenUiTreeV1;
  mode: 'deck' | 'document';
  pageSize?: 'A4' | 'Letter' | 'Slide16x9';
  orientation?: 'portrait' | 'landscape';
}

function defaultPageSize(mode: 'deck' | 'document'): 'A4' | 'Slide16x9' {
  return mode === 'deck' ? 'Slide16x9' : 'A4';
}

function defaultOrientation(mode: 'deck' | 'document'): 'portrait' | 'landscape' {
  return mode === 'deck' ? 'landscape' : 'portrait';
}

/** POST validated UI tree to backend; triggers browser download of PDF bytes. */
export async function exportGenUiTreeToPdf(opts: ExportGenUiPdfOptions): Promise<void> {
  const token = getAccessToken();
  const pageSize = opts.pageSize ?? defaultPageSize(opts.mode);
  const orientation = opts.orientation ?? defaultOrientation(opts.mode);
  const res = await fetch(`${API_BASE}/canvas/genui/export/pdf`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      session_id: opts.sessionId,
      message_id: opts.messageId ?? null,
      tree: opts.tree,
      mode: opts.mode,
      page_size: pageSize,
      orientation,
    }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || `PDF export failed (${res.status})`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const cd = res.headers.get('Content-Disposition');
  let filename = `genui-${Date.now()}.pdf`;
  if (cd) {
    const m = /filename="?([^";]+)"?/i.exec(cd);
    if (m?.[1]) filename = m[1];
  }
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
