/**
 * Live terminal store: consumes the per-session `tool_output_delta` SSE
 * stream (`GET /chat/sessions/{id}/terminal-stream`) so the workspace
 * terminal renders subprocess output while commands are still running,
 * instead of waiting for the final `tool_result`.
 *
 * `EventSource` can't send the Authorization header, so we use a streaming
 * `fetch` and parse SSE frames manually (same pattern as
 * `useCodingProjectLogs`).
 */
import { create } from 'zustand';
import { getAccessToken } from '@/api/client';
import { getMachineFingerprint } from '@/lib/machineFingerprint';

export interface TerminalChunk {
  tool_call_id: string;
  stream: 'stdout' | 'stderr' | 'system';
  data: string;
  seq: number;
  ts: number;
  tool_name: string;
  source: string; // shell | code | dev_server
  done?: boolean;
  exit_code?: number | null;
}

const MAX_CHUNKS_PER_SESSION = 4000;

/** Stable fallback so Zustand selectors do not re-render on every read. */
const EMPTY_CHUNKS: TerminalChunk[] = [];

interface TerminalState {
  chunksBySession: Record<string, TerminalChunk[]>;
  /** Live call ids (started but not yet done) per session. */
  liveCalls: Record<string, Set<string>>;
  connectedSessions: Set<string>;

  /** Open (or keep) the SSE subscription for a session. */
  connect: (sessionId: string) => void;
  disconnect: (sessionId: string) => void;
  clearSession: (sessionId: string) => void;
}

const controllers = new Map<string, AbortController>();

export const useTerminalStore = create<TerminalState>((set, get) => ({
  chunksBySession: {},
  liveCalls: {},
  connectedSessions: new Set(),

  connect: (sessionId) => {
    if (!sessionId || controllers.has(sessionId)) return;
    const controller = new AbortController();
    controllers.set(sessionId, controller);
    set((s) => ({
      connectedSessions: new Set([...s.connectedSessions, sessionId]),
    }));

    const url =
      (import.meta.env.VITE_API_BASE_URL || '/api/v1') +
      `/chat/sessions/${sessionId}/terminal-stream`;

    void (async () => {
      try {
        const headers: Record<string, string> = { Accept: 'text/event-stream' };
        const token = getAccessToken();
        if (token) headers.Authorization = `Bearer ${token}`;
        const fp = getMachineFingerprint();
        if (fp.length >= 8) headers['x-leagent-machine-fingerprint'] = fp;

        const resp = await fetch(url, {
          method: 'GET',
          credentials: 'include',
          headers,
          signal: controller.signal,
        });
        if (!resp.ok || !resp.body) return;

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        const handleData = (data: string) => {
          try {
            const frame = JSON.parse(data) as {
              type?: string;
              data?: TerminalChunk;
            };
            if (frame.type !== 'tool_output_delta' || !frame.data) return;
            appendChunk(sessionId, frame.data, set);
          } catch {
            /* malformed frame — skip */
          }
        };

        while (!controller.signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split('\n\n');
          buffer = blocks.pop() || '';
          for (const block of blocks) {
            for (const line of block.split('\n')) {
              if (line.startsWith('data:')) handleData(line.slice(5).trim());
            }
          }
        }
      } catch {
        /* aborted or network error — silent; reconnect happens on next connect() */
      } finally {
        controllers.delete(sessionId);
        set((s) => {
          const next = new Set(s.connectedSessions);
          next.delete(sessionId);
          return { connectedSessions: next };
        });
      }
    })();
  },

  disconnect: (sessionId) => {
    controllers.get(sessionId)?.abort();
    controllers.delete(sessionId);
  },

  clearSession: (sessionId) => {
    get().disconnect(sessionId);
    set((s) => {
      const chunks = { ...s.chunksBySession };
      delete chunks[sessionId];
      const live = { ...s.liveCalls };
      delete live[sessionId];
      return { chunksBySession: chunks, liveCalls: live };
    });
  },
}));

function appendChunk(
  sessionId: string,
  chunk: TerminalChunk,
  set: (fn: (s: TerminalState) => Partial<TerminalState>) => void,
) {
  set((s) => {
    const prev = s.chunksBySession[sessionId] ?? [];
    const next = [...prev, chunk];
    const bounded =
      next.length > MAX_CHUNKS_PER_SESSION
        ? next.slice(next.length - MAX_CHUNKS_PER_SESSION)
        : next;

    const live = new Set(s.liveCalls[sessionId] ?? []);
    if (chunk.done) live.delete(chunk.tool_call_id);
    else live.add(chunk.tool_call_id);

    return {
      chunksBySession: { ...s.chunksBySession, [sessionId]: bounded },
      liveCalls: { ...s.liveCalls, [sessionId]: live },
    };
  });
}

export function selectSessionChunks(
  state: TerminalState,
  sessionId: string | null,
): TerminalChunk[] {
  if (!sessionId) return EMPTY_CHUNKS;
  return state.chunksBySession[sessionId] ?? EMPTY_CHUNKS;
}
