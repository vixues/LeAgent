/**
 * URL safety allow-list for GenUI surfaces.
 *
 * GenUI trees are model-authored and therefore untrusted. Any URL that becomes
 * an `<a href>`, a `window.open` target, or an `<img src>` must pass through
 * here so dangerous schemes (`javascript:`, `vbscript:`, non-image `data:`,
 * `file:`) can never execute or exfiltrate.
 */

/** Schemes allowed for navigation / link targets. */
const SAFE_LINK_SCHEMES = new Set(['http:', 'https:', 'mailto:', 'tel:']);

/** Resolve a URL's scheme (lowercased, with trailing colon) or null. */
function schemeOf(url: string): string | null {
  const match = /^([a-z][a-z0-9+.-]*):/i.exec(url.trim());
  const scheme = match?.[1];
  return scheme ? `${scheme.toLowerCase()}:` : null;
}

/**
 * True when `url` is safe to use as a link / navigation target.
 * Relative URLs (path, query, fragment) and the listed schemes are allowed.
 */
export function isSafeHref(url: unknown): url is string {
  if (typeof url !== 'string') return false;
  const trimmed = url.trim();
  if (!trimmed) return false;
  const scheme = schemeOf(trimmed);
  if (scheme === null) return true;
  return SAFE_LINK_SCHEMES.has(scheme);
}

/** Return `url` when safe, otherwise `null`. */
export function safeHref(url: unknown): string | null {
  return isSafeHref(url) ? url.trim() : null;
}
