import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

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

export function useRealtimeFileSync(enabled = true) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!enabled) return;

    let eventSource: EventSource | null = null;
    let reconnectTimer: number | null = null;
    let reconnectDelayMs = 1500;
    let disposed = false;

    const invalidateFileQueries = () => {
      queryClient.invalidateQueries({
        predicate: (q) => isFolderOrDocumentKey(q.queryKey),
      });
    };

    const onLocalEvent = () => invalidateFileQueries();
    window.addEventListener(
      LOCAL_EVENT_NAME,
      onLocalEvent as EventListener,
    );

    const connect = () => {
      if (disposed) return;
      try {
        const fp = encodeURIComponent(getMachineFingerprint());
        const sep = SSE_URL.includes('?') ? '&' : '?';
        eventSource = new EventSource(`${SSE_URL}${sep}leagent_machine_fp=${fp}`, {
          withCredentials: true,
        });
      } catch {
        reconnectTimer = window.setTimeout(connect, reconnectDelayMs);
        reconnectDelayMs = Math.min(reconnectDelayMs * 2, 15000);
        return;
      }

      eventSource.onmessage = () => {
        reconnectDelayMs = 1500;
        invalidateFileQueries();
      };

      eventSource.onerror = () => {
        eventSource?.close();
        eventSource = null;
        if (!disposed) {
          reconnectTimer = window.setTimeout(connect, reconnectDelayMs);
          reconnectDelayMs = Math.min(reconnectDelayMs * 2, 15000);
        }
      };
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
      eventSource?.close();
      window.removeEventListener(
        LOCAL_EVENT_NAME,
        onLocalEvent as EventListener,
      );
    };
  }, [enabled, queryClient]);
}
