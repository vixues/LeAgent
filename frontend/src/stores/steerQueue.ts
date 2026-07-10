import { create } from 'zustand';
import { apiClient } from '@/api/client';

export interface QueuedChatMessage {
  id: string;
  content: string;
  created_at: number;
}

/** Stable fallback so Zustand selectors do not re-render on every read. */
const EMPTY_QUEUED: QueuedChatMessage[] = [];

export interface SteerResponse {
  session_id: string;
  queued_for_injection: boolean;
  message_id: string | null;
}

interface SteerQueueState {
  /** Messages queued for dispatch after the current turn, per session. */
  queuedBySession: Record<string, QueuedChatMessage[]>;

  /** Inject a user message into the running turn (Codex-style steer). */
  steer: (sessionId: string, message: string) => Promise<SteerResponse>;
  /** Queue a message for the next turn. */
  queueMessage: (sessionId: string, message: string) => Promise<QueuedChatMessage>;
  /** Remove a queued message before dispatch. */
  removeQueued: (sessionId: string, messageId: string) => Promise<void>;
  /** Pop the next queued message (returns null when the queue is empty). */
  popNextQueued: (sessionId: string) => Promise<QueuedChatMessage | null>;
  /** Refresh the queue snapshot from the server. */
  refreshQueue: (sessionId: string) => Promise<void>;
}

export const useSteerQueueStore = create<SteerQueueState>((set) => ({
  queuedBySession: {},

  steer: async (sessionId, message) => {
    return apiClient.post<SteerResponse>(`/chat/sessions/${sessionId}/steer`, {
      message,
    });
  },

  queueMessage: async (sessionId, message) => {
    const res = await apiClient.post<{ queued: QueuedChatMessage }>(
      `/chat/sessions/${sessionId}/queue`,
      { message },
    );
    set((s) => ({
      queuedBySession: {
        ...s.queuedBySession,
        [sessionId]: [...(s.queuedBySession[sessionId] ?? []), res.queued],
      },
    }));
    return res.queued;
  },

  removeQueued: async (sessionId, messageId) => {
    await apiClient.delete(`/chat/sessions/${sessionId}/queue/${messageId}`);
    set((s) => ({
      queuedBySession: {
        ...s.queuedBySession,
        [sessionId]: (s.queuedBySession[sessionId] ?? []).filter((m) => m.id !== messageId),
      },
    }));
  },

  popNextQueued: async (sessionId) => {
    const res = await apiClient.post<{ message: QueuedChatMessage | null }>(
      `/chat/sessions/${sessionId}/queue/pop`,
    );
    const popped = res.message;
    if (popped) {
      set((s) => ({
        queuedBySession: {
          ...s.queuedBySession,
          [sessionId]: (s.queuedBySession[sessionId] ?? []).filter((m) => m.id !== popped.id),
        },
      }));
    }
    return popped;
  },

  refreshQueue: async (sessionId) => {
    const res = await apiClient.get<{ queued: QueuedChatMessage[] }>(
      `/chat/sessions/${sessionId}/queue`,
    );
    set((s) => ({
      queuedBySession: { ...s.queuedBySession, [sessionId]: res.queued ?? [] },
    }));
  },
}));

export function getQueuedForSession(
  state: SteerQueueState,
  sessionId: string | null,
): QueuedChatMessage[] {
  if (!sessionId) return EMPTY_QUEUED;
  return state.queuedBySession[sessionId] ?? EMPTY_QUEUED;
}
