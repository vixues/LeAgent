import { useQuery } from '@tanstack/react-query';
import { apiClient, HttpError } from '@/api/client';
import { isUuid } from '@/lib/utils';
import {
  getSessionProjectHeaders,
  isSessionProjectUnlocked,
  useChatStore,
} from '@/stores/chat';

export interface AgentMemoryEpisode {
  id: string;
  session_id: string;
  user_id: string | null;
  summary: string;
  tags: string[];
  importance: number;
  token_count: number | null;
  recall_count: number;
  last_recalled_at: string | null;
  created_at: string | null;
}

export interface AgentMemoryFact {
  id: string;
  key: string;
  value: string;
  confidence: number;
  source: string | null;
  workspace_id: string | null;
  created_at: string | null;
}

export interface AgentMemoryProcedure {
  id: string;
  name: string;
  signature: string;
  description: string;
  run_count: number;
  success_count: number;
  success_rate: number;
  last_outcome: string | null;
  last_run_at: string | null;
  created_at: string | null;
}

export interface AgentMemorySnapshot {
  enabled: boolean;
  episodes: AgentMemoryEpisode[];
  facts: AgentMemoryFact[];
  procedures: AgentMemoryProcedure[];
}

export function useAgentMemorySnapshot(options: {
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
    queryKey: ['agent-memory', sessionId],
    queryFn: () =>
      apiClient.get<AgentMemorySnapshot>(
        `/chat/sessions/${sessionId}/agent-memory`,
        undefined,
        { headers: getSessionProjectHeaders(sessionId!) },
      ),
    enabled:
      isUuid(sessionId) &&
      enabled &&
      !isPending &&
      chatSessionsReconciled &&
      projectUnlocked,
    staleTime: 30_000,
    retry: (failureCount, err) => {
      if (err instanceof HttpError && (err.status === 404 || err.status === 423)) return false;
      return failureCount < 2;
    },
  });
}
