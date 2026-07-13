import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { getAccessToken } from '@/api/client';
import { getMachineFingerprint } from '@/lib/machineFingerprint';

type RealtimeFileEvent =
  | 'uploaded'
  | 'updated'
  | 'deleted'
  | 'indexed'
  | 'refresh';

interface RealtimeFileEventDetail {
  type: RealtimeFileEvent;
}

const LOCAL_EVENT_NAME = 'leagent:file-event';
const SSE_URL =
  import.meta.env.VITE_FILE_EVENTS_SSE_URL || '/api/v1/files/events/stream';

function isFolderOrDocumentKey(key: readonly unknown[]): boolean {
  if (key.length === 0) return false;
  const prefix = key[0];
  return prefix === 'folders' || prefix === 'documents';
}

export function emitRealtimeFileEvent(type: RealtimeFileEvent = 'refresh') {
  window.dispatchEvent(
    new CustomEvent<RealtimeFileEventDetail>(LOCAL_EVENT_NAME, {
      detail: { type },
    }),
  );
}

/**
 * File-sync subscription.
 *
 * Uses fetch-based SSE (not ``EventSource``) so the Authorization bearer can
 * be sent when auth is enforced — same pattern as the terminal stream.
 */
export function useRealtimeFileSync(enabled = true) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!enabled) return;

    let abort: AbortController | null = null;
    let reconnectTimer: number | null = null;
    let reconnectDelayMs = 1500;
    let disposed = false;

    const invalidateFileQueries = () => {
      queryClient.invalidateQueries({
        predicate: (q) => isFolderOrDocumentKey(q.queryKey),
      });
    };

    const onLocalEvent = () => invalidateFileQueries();
    window.addEventListener(LOCAL_EVENT_NAME, onLocalEvent as EventListener);

    const connect = () => {
      if (disposed) return;
      abort?.abort();
      abort = new AbortController();
      const fp = encodeURIComponent(getMachineFingerprint());
      const sep = SSE_URL.includes('?') ? '&' : '?';
      const url = `${SSE_URL}${sep}leagent_machine_fp=${fp}`;
      const token = getAccessToken();
      void (async () => {
        try {
          const res = await fetch(url, {
            headers: {
              Accept: 'text/event-stream',
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            credentials: 'include',
            signal: abort?.signal,
          });
          if (!res.ok || !res.body) {
            throw new Error(`SSE HTTP ${res.status}`);
          }
          reconnectDelayMs = 1500;
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const chunks = buffer.split('\n\n');
            buffer = chunks.pop() || '';
            for (const chunk of chunks) {
              if (chunk.trim()) invalidateFileQueries();
            }
          }
        } catch (err) {
          if (abort?.signal.aborted || disposed) return;
          reconnectTimer = window.setTimeout(connect, reconnectDelayMs);
          reconnectDelayMs = Math.min(reconnectDelayMs * 2, 15000);
          void err;
        }
      })();
    };

    connect();

    return () => {
      disposed = true;
      abort?.abort();
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
      window.removeEventListener(LOCAL_EVENT_NAME, onLocalEvent as EventListener);
    };
  }, [enabled, queryClient]);
}
