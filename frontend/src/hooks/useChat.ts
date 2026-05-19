import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import i18n from '@/i18n';
import { apiClient } from '@/api/client';
import { useChatStore } from '@/stores/chat';
import type {
  AuthorizedPathCreateBody,
  AuthorizedPathsResponse,
  ChatSession,
  Message,
} from '@/types/chat';
import { normalizeMessageList, type MessageResponse } from '@/types/chatHistory';

interface SessionResponse {
  id: string;
  name: string;
  user_id: string;
  flow_id?: string;
  is_active: boolean;
  message_count: number;
  last_message_at?: string;
  created_at: string;
  updated_at: string;
  pinned_message_ids?: string[];
}

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_prev: boolean;
}

function mapSession(s: SessionResponse): ChatSession {
  const pins = s.pinned_message_ids;
  return {
    id: s.id,
    title: s.name || i18n.t('chat.defaultSessionName'),
    createdAt: s.created_at,
    updatedAt: s.updated_at,
    messageCount: s.message_count,
    preview: undefined,
    pinnedMessageIds: Array.isArray(pins) ? pins.map(String) : [],
  };
}

const CHAT_KEYS = {
  sessions: ['chat', 'sessions'] as const,
  session: (id: string) => ['chat', 'sessions', id] as const,
  messages: (sessionId: string) => ['chat', 'sessions', sessionId, 'messages'] as const,
  authorizedPaths: (sessionId: string) =>
    ['chat', 'sessions', sessionId, 'authorized-paths'] as const,
};

export function useChatSessions(page = 1, pageSize = 50) {
  return useQuery({
    queryKey: [...CHAT_KEYS.sessions, page, pageSize],
    queryFn: async () => {
      const res = await apiClient.get<PaginatedResponse<SessionResponse>>(
        '/chat/sessions',
        { page, page_size: pageSize }
      );
      return {
        ...res,
        items: res.items.map(mapSession),
      };
    },
    staleTime: 30_000,
  });
}

export function useChatMessages(sessionId: string | null, page = 1, pageSize = 100) {
  const chatSessionsReconciled = useChatStore((s) => s.chatSessionsReconciled);
  return useQuery({
    queryKey: sessionId ? [...CHAT_KEYS.messages(sessionId), page] : ['chat', 'no-session'],
    queryFn: async () => {
      if (!sessionId) return { items: [] as Message[], total: 0 };
      const res = await apiClient.get<PaginatedResponse<MessageResponse>>(
        `/chat/sessions/${sessionId}/messages`,
        { page, page_size: pageSize }
      );
      return {
        ...res,
        items: normalizeMessageList(res.items),
      };
    },
    enabled: !!sessionId && chatSessionsReconciled,
    staleTime: 10_000,
  });
}

export function useSessionAuthorizedPaths(sessionId: string | null) {
  const chatSessionsReconciled = useChatStore((s) => s.chatSessionsReconciled);
  return useQuery({
    queryKey: sessionId
      ? CHAT_KEYS.authorizedPaths(sessionId)
      : ['chat', 'no-session', 'authorized-paths'],
    queryFn: async () => {
      if (!sessionId) return { session_id: '', paths: [] } satisfies AuthorizedPathsResponse;
      return apiClient.get<AuthorizedPathsResponse>(
        `/chat/sessions/${sessionId}/authorized-paths`
      );
    },
    enabled: !!sessionId && chatSessionsReconciled,
    staleTime: 10_000,
  });
}

export function useAddAuthorizedPath() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      sessionId,
      body,
    }: {
      sessionId: string;
      body: AuthorizedPathCreateBody;
    }) =>
      apiClient.post<AuthorizedPathsResponse>(
        `/chat/sessions/${sessionId}/authorized-paths`,
        body
      ),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: CHAT_KEYS.authorizedPaths(variables.sessionId),
      });
    },
  });
}

export function useRemoveAuthorizedPath() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ sessionId, path }: { sessionId: string; path: string }) =>
      apiClient.delete<AuthorizedPathsResponse>(
        `/chat/sessions/${sessionId}/authorized-paths?path=${encodeURIComponent(path)}`
      ),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: CHAT_KEYS.authorizedPaths(variables.sessionId),
      });
    },
  });
}

export function useCreateSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: { name?: string; flow_id?: string }) => {
      const res = await apiClient.post<SessionResponse>('/chat/sessions', params);
      return mapSession(res);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CHAT_KEYS.sessions });
    },
  });
}

export function useDeleteSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) =>
      apiClient.delete(`/chat/sessions/${sessionId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CHAT_KEYS.sessions });
    },
  });
}

export function useUpdateSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ sessionId, name }: { sessionId: string; name: string }) => {
      const res = await apiClient.patch<SessionResponse>(
        `/chat/sessions/${sessionId}`,
        { name }
      );
      return mapSession(res);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CHAT_KEYS.sessions });
    },
  });
}

// ---------------------------------------------------------------------------
// Local directory browser
// ---------------------------------------------------------------------------

export interface BrowseDirEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

export interface BrowseDirectoriesResponse {
  path: string;
  parent: string | null;
  entries: BrowseDirEntry[];
  quick_access: BrowseDirEntry[];
}

export function useBrowseDirectories(dirPath: string | null) {
  return useQuery({
    queryKey: ['chat', 'browse-directories', dirPath ?? '~'],
    queryFn: () =>
      apiClient.get<BrowseDirectoriesResponse>(
        '/chat/browse-directories',
        dirPath ? { path: dirPath } : undefined,
      ),
    enabled: dirPath !== undefined,
    staleTime: 5_000,
    placeholderData: keepPreviousData,
  });
}

export { CHAT_KEYS };
