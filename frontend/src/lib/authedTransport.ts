/**
 * Auth-aware browser transports (WebSocket / helpers).
 *
 * EventSource cannot send Authorization; prefer fetch-based SSE (see
 * ``stores/terminal.ts``) or attach a short-lived ``?token=`` only when needed.
 * WebSockets prefer ``Sec-WebSocket-Protocol: bearer,<token>`` with a query
 * fallback for environments that reject custom protocols.
 */
import { getAccessToken } from '@/api/client';

/** Append ``token`` query when a session JWT is available. */
export function withAccessTokenQuery(url: string): string {
  const token = getAccessToken();
  if (!token) return url;
  try {
    const absolute = url.startsWith('ws:') || url.startsWith('wss:')
      ? url.replace(/^ws/i, 'http')
      : url;
    const u = new URL(absolute, typeof window !== 'undefined' ? window.location.origin : 'http://localhost');
    if (!u.searchParams.has('token')) {
      u.searchParams.set('token', token);
    }
    if (url.startsWith('ws:') || url.startsWith('wss:')) {
      u.protocol = url.startsWith('wss:') ? 'wss:' : 'ws:';
    }
    return u.toString();
  } catch {
    const sep = url.includes('?') ? '&' : '?';
    return `${url}${sep}token=${encodeURIComponent(token)}`;
  }
}

/**
 * Open a WebSocket with session credentials.
 * Tries subprotocol ``bearer`` + token first; falls back to ``?token=``.
 */
export function openAuthedWebSocket(url: string): WebSocket {
  const token = getAccessToken();
  if (!token) {
    return new WebSocket(url);
  }
  try {
    return new WebSocket(url, ['bearer', token]);
  } catch {
    return new WebSocket(withAccessTokenQuery(url));
  }
}
