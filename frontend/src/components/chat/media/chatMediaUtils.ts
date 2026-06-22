const API_FILE_PREVIEW_RE = /\/files\/([^/]+)\/preview\/?$/i;
const API_FILE_DOWNLOAD_RE = /\/files\/([^/]+)\/download\/?$/i;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function parseUrl(src: string | undefined): URL | null {
  if (!src?.trim()) return null;
  try {
    const base =
      typeof window !== 'undefined' ? window.location.origin : 'http://local.invalid';
    return src.startsWith('http://') || src.startsWith('https://')
      ? new URL(src)
      : new URL(src, base);
  } catch {
    return null;
  }
}

/** Resolve UUID from ``…/files/{id}/preview`` paths or full URLs. */
export function extractApiFilePreviewId(src: string | undefined): string | null {
  const u = parseUrl(src);
  const m = u?.pathname.match(API_FILE_PREVIEW_RE);
  const id = m?.[1] ?? '';
  return UUID_RE.test(id) ? id : null;
}

/** Resolve UUID from ``…/files/{id}/download`` paths or full URLs. */
export function extractApiFileDownloadId(src: string | undefined): string | null {
  const u = parseUrl(src);
  const m = u?.pathname.match(API_FILE_DOWNLOAD_RE);
  const id = m?.[1] ?? '';
  return UUID_RE.test(id) ? id : null;
}

/** Return the UUID only when the caller should fetch the preview with bearer auth. */
export function extractAuthedApiFilePreviewId(src: string | undefined): string | null {
  const u = parseUrl(src);
  if (!u || u.searchParams.has('token')) return null;
  return extractApiFilePreviewId(src);
}

/** True for malformed managed-file preview paths such as ``/files/name/preview``. */
export function isInvalidApiFilePreviewRef(src: string | undefined): boolean {
  const u = parseUrl(src);
  const m = u?.pathname.match(API_FILE_PREVIEW_RE);
  if (!m) return false;
  return !UUID_RE.test(m[1] ?? '');
}

const VIDEO_EXT_RE = /\.(mp4|webm|ogg|mov|m4v)(\?|#|$)/i;

/** True when ``src`` is a managed ``/files/{uuid}/preview`` URL that includes a ``token=`` query (browser-loadable without Bearer). */
export function managedFilePreviewHasSignedToken(src: string | undefined): boolean {
  return Boolean(parseUrl(src)?.searchParams.get('token')) && extractApiFilePreviewId(src) !== null;
}

export function isProbablyVideoUrl(href: string | undefined): boolean {
  if (!href) return false;
  return VIDEO_EXT_RE.test(href);
}

export function isRtspUrl(href: string | undefined): boolean {
  if (!href) return false;
  const h = href.trim().toLowerCase();
  return h.startsWith('rtsp://') || h.startsWith('rtsps://');
}

const URL_SCHEME_RE = /^[a-z][a-z0-9+.-]*:/i;

export interface MarkdownImageAttachmentLike {
  id?: string;
  name: string;
  previewUrl?: string;
  downloadUrl?: string;
  url?: string;
}

const CHAT_MEDIA_API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

function pickAttachmentPreviewHref(att: MarkdownImageAttachmentLike): string | undefined {
  const href = att.previewUrl ?? att.url ?? att.downloadUrl;
  if (href) return href;
  const id = att.id?.trim();
  if (id && UUID_RE.test(id)) {
    const prefix = CHAT_MEDIA_API_BASE.replace(/\/$/, '');
    return `${prefix}/files/${id}/preview`;
  }
  return undefined;
}

function pathBasename(path: string): string {
  const norm = path.replace(/\\/g, '/').trim();
  const i = norm.lastIndexOf('/');
  return i >= 0 ? norm.slice(i + 1) : norm;
}

/**
 * When the model embeds ``![](plot.png)`` or ``![](out/plot.png)`` after a tool saved a file
 * that was registered as a chat attachment, rewrite ``src`` to that attachment's preview URL.
 * Leaves http(s), ``data:``, ``blob:``, and existing ``/api/v1/files/{uuid}/preview`` refs unchanged.
 */
export function resolveMarkdownImageSrcFromAttachments(
  src: string | undefined,
  attachments: readonly MarkdownImageAttachmentLike[] | undefined,
  fallbackName?: string,
): string | undefined {
  const raw = src?.trim();
  const fallback = fallbackName?.trim();
  if (!attachments?.length) return src;
  if (!raw && !fallback) return src;

  if (raw && URL_SCHEME_RE.test(raw)) {
    const scheme = raw.slice(0, raw.indexOf(':') + 1).toLowerCase();
    if (scheme === 'http:' || scheme === 'https:' || scheme === 'data:' || scheme === 'blob:') {
      return src;
    }
  }

  if (raw?.startsWith('//')) return src;

  if (raw && extractApiFilePreviewId(raw) !== null) return src;

  const candidate = pathBasename(raw || fallback || '');
  if (!candidate || candidate.includes('..')) return src;

  const candLower = candidate.toLowerCase();
  for (let i = attachments.length - 1; i >= 0; i -= 1) {
    const att = attachments[i]!;
    const base = pathBasename(att.name);
    if (base.toLowerCase() !== candLower) continue;
    const href = pickAttachmentPreviewHref(att);
    if (href) return href;
  }

  return src;
}
