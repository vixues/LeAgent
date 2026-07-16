/** Allow navigation only to local backend / Vite / file URLs used by splash & maintenance. */
export function isAllowedNavigationUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'file:') return true;
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return false;
    const host = parsed.hostname;
    return host === '127.0.0.1' || host === 'localhost';
  } catch {
    return false;
  }
}
