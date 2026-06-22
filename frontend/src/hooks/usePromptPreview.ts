import { useQuery } from '@tanstack/react-query';
import { apiClient, HttpError } from '@/api/client';
import { isUuid } from '@/lib/utils';
import {
  getSessionProjectHeaders,
  isSessionProjectUnlocked,
  useChatStore,
} from '@/stores/chat';

export interface PromptLayer {
  name: string;
  body: string;
  tokens: number;
  truncated: boolean;
}

export interface PromptPreview {
  query_used: string;
  system_text: string;
  total_chars: number;
  stable_hash: string;
  full_hash: string;
  variant_key: string;
  layers: PromptLayer[];
  /** Approximate transcript tokens (same heuristic as session compression). */
  approx_transcript_tokens?: number;
  /** System prompt layers + transcript approximation for context pressure UI. */
  approx_context_tokens?: number;
}

export function usePromptPreview(options: {
  sessionId: string | null | undefined;
  enabled?: boolean;
}) {
  const { sessionId, enabled = true } = options;
  const isPending = useChatStore((s) =>
    sessionId ? s.sessions.find((x) => x.id === sessionId)?.isPending === true : false,
  );
  const chatSessionsReconciled = useChatStore((s) => s.chatSessionsReconciled);
  const projectUnlocked =
    sessionId && isUuid(sessionId) ? isSessionProjectUnlocked(sessionId) : true;
  return useQuery({
    queryKey: ['prompt-preview', sessionId],
    queryFn: () =>
      apiClient.get<PromptPreview>(
        `/chat/sessions/${sessionId}/prompt-preview`,
        undefined,
        { headers: getSessionProjectHeaders(sessionId!) },
      ),
    enabled:
      isUuid(sessionId) &&
      enabled &&
      !isPending &&
      chatSessionsReconciled &&
      projectUnlocked,
    staleTime: 15_000,
    refetchOnMount: 'always',
    retry: (failureCount, err) => {
      if (err instanceof HttpError && (err.status === 404 || err.status === 423)) return false;
      return failureCount < 2;
    },
  });
}
