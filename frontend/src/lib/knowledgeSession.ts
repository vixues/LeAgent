import { apiClient, HttpError } from '@/api/client';

const KNOWLEDGE_SESSION_KEY = 'leagent-knowledge-session-id';

let inFlight: Promise<string> | null = null;

/** Drop cached knowledge session id (e.g. after logout or when the server rejects it). */
export function clearKnowledgeSessionId(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(KNOWLEDGE_SESSION_KEY);
}

/**
 * Resolves a dedicated chat session id for indexed document (knowledge) uploads.
 * Persists in localStorage so all catalogued files share one session row.
 *
 * If the cached id no longer exists for the current user (DB reset, session deleted,
 * or account switch), it is cleared and a new session is created.
 */
export async function getOrCreateKnowledgeSessionId(): Promise<string> {
  if (typeof window === 'undefined') {
    throw new Error('Knowledge session id is only available in the browser');
  }
  const existing = localStorage.getItem(KNOWLEDGE_SESSION_KEY);
  if (existing) {
    try {
      await apiClient.get(`/chat/sessions/${existing}`);
      return existing;
    } catch (e) {
      if (e instanceof HttpError && e.status === 404) {
        clearKnowledgeSessionId();
      } else {
        throw e;
      }
    }
  }
  if (inFlight) {
    return inFlight;
  }
  inFlight = (async () => {
    const res = await apiClient.post<{ id: string }>('/chat/sessions', {
      name: 'Knowledge base',
    });
    const id = String(res.id);
    localStorage.setItem(KNOWLEDGE_SESSION_KEY, id);
    return id;
  })().finally(() => {
    inFlight = null;
  });
  return inFlight;
}
