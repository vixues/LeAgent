import { getAccessToken } from '@/api/client';

const API_PREFIX = import.meta.env.VITE_API_BASE_URL || '/api/v1';

function parseFilenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null;
  const star = /filename\*=UTF-8''([^;\s]+)/i.exec(header);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].replace(/^"|"$/g, ''));
    } catch {
      return star[1];
    }
  }
  const quoted = /filename="([^"]+)"/i.exec(header);
  if (quoted?.[1]) return quoted[1];
  const plain = /filename=([^;\s]+)/i.exec(header);
  if (plain?.[1]) return plain[1].replace(/^"|"$/g, '');
  return null;
}

/**
 * Download a stored file using the JWT (plain navigation cannot send `Authorization`).
 * Uses `GET …/files/{id}/download` which accepts Bearer or a signed `?token=`.
 */
export async function downloadAuthenticatedFile(
  fileId: string,
  fallbackFilename: string,
): Promise<void> {
  const token = getAccessToken();
  const url = `${API_PREFIX.replace(/\/$/, '')}/files/${fileId}/download`;
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    credentials: 'include',
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const headerName = parseFilenameFromContentDisposition(
    res.headers.get('Content-Disposition'),
  );
  const filename = headerName || fallbackFilename;
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(objectUrl);
}

/** Open a managed file preview in a new tab via an authenticated blob URL. */
export async function openAuthenticatedFilePreview(fileId: string): Promise<void> {
  const token = getAccessToken();
  const url = `${API_PREFIX.replace(/\/$/, '')}/files/${fileId}/preview`;
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    credentials: 'include',
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const opened = window.open(objectUrl, '_blank', 'noopener,noreferrer');
  if (!opened) {
    URL.revokeObjectURL(objectUrl);
    throw new Error('Popup blocked');
  }
  // Revoke after the tab has a chance to load the blob.
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}
