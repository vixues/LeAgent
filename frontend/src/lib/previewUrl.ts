const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

/** Token-gated coding-project reverse proxy (see backend coding_projects router). */
const CODING_PROJECT_PREVIEW_PATH =
  /^\/api\/v1\/coding-projects\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/preview(?:\/|$)/i;

function isCodingProjectPreviewPath(pathname: string): boolean {
  return CODING_PROJECT_PREVIEW_PATH.test(pathname);
}

/**
 * Rewrite assistant markdown that used a wrong absolute origin (e.g. ``https://leagent.dev``)
 * so preview links hit this deployment's API (Vite proxy or ``VITE_API_BASE_URL``).
 */
export function resolveCodingProjectPreviewHref(
  href: string,
  apiBase: string = import.meta.env.VITE_API_BASE_URL || '/api/v1',
): string {
  if (!href || typeof href !== 'string') return href;
  const trimmed = href.trim();
  if (!trimmed) return href;

  try {
    let pathname: string;
    let search: string;
    let hash: string;

    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
      const u = new URL(trimmed);
      pathname = u.pathname;
      search = u.search;
      hash = u.hash;
    } else if (trimmed.startsWith('/')) {
      const u = new URL(trimmed, 'http://local.invalid');
      pathname = u.pathname;
      search = u.search;
      hash = u.hash;
    } else {
      return href;
    }

    if (!isCodingProjectPreviewPath(pathname)) {
      return href;
    }

    const pathWithQuery = pathname + search + hash;
    const base = apiBase.trim() || '/api/v1';

    if (base.startsWith('http://') || base.startsWith('https://')) {
      return new URL(pathWithQuery, base).href;
    }

    return pathWithQuery;
  } catch {
    return href;
  }
}

/**
 * Read hosted canvas preview path from artifact metadata (SSE uses camelCase;
 * persisted or API payloads may use snake_case or absolute preview_url).
 */
export function pickCanvasPreviewPathFromMetadata(
  metadata: Record<string, unknown> | undefined,
): string | null {
  if (!metadata) return null;
  const candidates = [
    metadata.previewPath,
    metadata.preview_path,
    metadata.preview_url,
    metadata.previewUrl,
  ];
  for (const v of candidates) {
    if (typeof v === 'string') {
      const s = v.trim();
      if (s.length > 0) return s;
    }
  }
  return null;
}

/**
 * Turn a `preview_path` from the canvas API (e.g. `/api/v1/canvas/preview?token=...`)
 * into a browser-usable URL. Vite dev proxies `/api` to the backend.
 */
export function resolveCanvasPreviewUrl(previewPath: string): string {
  if (!previewPath) return '';
  if (previewPath.startsWith('http://') || previewPath.startsWith('https://')) {
    return previewPath;
  }
  if (previewPath.startsWith('/')) {
    return previewPath;
  }
  if (previewPath.startsWith('api/')) {
    return `/${previewPath}`;
  }
  return `${API_BASE.replace(/\/$/, '')}/${previewPath.replace(/^\//, '')}`;
}
