import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import i18n from '@/i18n';
import { apiClient, HttpError } from '@/api/client';
import { generateId, isUuid } from '@/lib/utils';
import { useArtifactStore } from './artifact';
import { useChatDraftStore } from './chatDraft';
import { useLayoutStore } from './layout';
import { hydrateSessionCanvasArtifacts } from './artifact';
import { hydrateGenUiFromMessages, useGenUiStore } from './genUi';
import { useExecutionSessionStore } from './executionSession';
import { getChatProjectHeaders, useChatProjectStore } from './chatProjects';
import {
  ensureChronologicalMessages,
  normalizeMessageList,
  type MessageResponse,
} from '@/types/chatHistory';
import { enrichMessagesWithSessionAttachments } from '@/lib/chatAttachments';
import { queryClient } from '@/lib/queryClient';
import {
  namespacedPersistName,
  registerNamespacedStore,
} from '@/lib/persistNamespace';
import type {
  ChatSession,
  ChatWorkflowStepRunRecord,
  Message,
  NestedAgentPreviewState,
  PendingUserInput,
  TaskProgressStep,
  ToolCall,
} from '@/types/chat';

const CHAT_STORE_BASE = 'leagent-chat';
registerNamespacedStore(CHAT_STORE_BASE);
const CHAT_MESSAGES_PAGE_SIZE = 80;

/** Invalidates in-flight GET /messages responses when switching threads quickly. */
let messagesFetchSeq = 0;

interface MessagePageState {
  hasOlder: boolean;
  nextOlderPage: number;
  isLoadingOlder: boolean;
}

interface SessionTodoUiState {
  pinned: boolean;
  dismissed: boolean;
}

interface ChatStore {
  sessions: ChatSession[];
  currentSessionId: string | null;
  messages: Record<string, Message[]>;
  messagePages: Record<string, MessagePageState>;
  /** When set, `fetchMessages` is in flight for this session (used to avoid empty-state layout flash). */
  messagesLoadingSessionId: string | null;
  /**
   * Which session owns the in-flight `/chat/stream` (loading/streaming flags match this id).
   * Lets the composer stay usable on other threads while a long coding run finishes elsewhere.
   */
  activeStreamSessionId: string | null;
  isLoading: boolean;
  isStreaming: boolean;
  error: string | null;
  synced: boolean;
  /** True after the first ``fetchSessions`` attempt (success or failure). Gates session-scoped queries until persisted thread ids are reconciled with the server. */
  chatSessionsReconciled: boolean;
  /** Active ``ask_user`` questionnaire for the current thread (not persisted). */
  pendingUserInput: PendingUserInput | null;
  /** Active `/chat/stream` fetch — survives ChatView unmount so navigation does not abort SSE. */
  streamAbortController: AbortController | null;

  /** Sub-agent (coding_agent child) tool-arg stream — keyed by session id; live-only. */
  nestedAgentPreviewBySession: Record<string, NestedAgentPreviewState | null>;
  setNestedAgentPreview: (sessionId: string, preview: NestedAgentPreviewState | null) => void;

  fetchSessions: (projectId?: string | null) => Promise<void>;
  createSession: (title?: string, projectId?: string | null) => Promise<string>;
  deleteSession: (id: string) => Promise<void>;
  /** Server returned 404 — remove thread from local state without calling DELETE. */
  dropStaleSession: (id: string) => void;
  selectSession: (id: string) => void;
  updateSessionTitle: (id: string, title: string) => void;
  fetchMessages: (sessionId: string) => Promise<void>;
  fetchOlderMessages: (sessionId: string) => Promise<void>;

  addMessage: (sessionId: string, message: Message) => void;
  /** Insert a mid-turn steer user row before the in-flight assistant message. */
  insertSteerMessage: (sessionId: string, message: Message) => void;
  updateMessage: (sessionId: string, messageId: string, updates: Partial<Message>) => void;
  appendToMessage: (sessionId: string, messageId: string, content: string) => void;
  updateToolCall: (sessionId: string, messageId: string, toolCallId: string, updates: Partial<ToolCall>) => void;
  finalizeToolCalls: (
    sessionId: string,
    messageId: string,
    terminalStatus?: Extract<ToolCall['status'], 'success' | 'error'>,
  ) => void;
  upsertTaskProgress: (sessionId: string, messageId: string, step: TaskProgressStep) => void;
  finalizeTaskProgress: (
    sessionId: string,
    messageId: string,
    terminalStatus?: TaskProgressStep['status'],
  ) => void;
  updateWorkflowStepRun: (
    sessionId: string,
    messageId: string,
    stepId: string,
    partial: Partial<ChatWorkflowStepRunRecord>,
  ) => void;
  clearMessages: (sessionId: string) => void;
  /** Keep messages up to and including `messageId`; drop the rest. Returns false if id not found. */
  truncateAfterMessageId: (sessionId: string, messageId: string) => boolean;

  /** Map optimistic client message ids to DB UUIDs after `/chat/stream` persist (SSE `message_ids`). */
  remapStreamPersistedIds: (
    sessionId: string,
    mapping: {
      clientUserId: string;
      serverUserId?: string;
      clientAssistantId: string;
      serverAssistantId?: string;
    },
  ) => void;

  setLoading: (loading: boolean) => void;
  setStreaming: (streaming: boolean) => void;
  /** Claim this session as the active stream owner (sets loading + streaming). */
  beginChatStreamSession: (sessionId: string) => void;
  /** Clear loading/streaming only if this session still owns the stream (safe across abort races). */
  releaseChatStreamSession: (sessionId: string) => void;
  /** Release stream ownership and reload canonical message order from the server. */
  releaseChatStreamSessionAndResync: (sessionId: string) => void;
  /** Abort the current fetch if it belongs to another session (before starting a new stream). */
  abortActiveStreamUnlessSession: (sessionId: string) => void;
  setError: (error: string | null) => void;
  setPendingUserInput: (payload: PendingUserInput | null) => void;
  clearPendingUserInput: () => void;
  setStreamAbortController: (controller: AbortController | null) => void;
  /** Clear ref only if it still points to this instance (avoids races with a newer stream). */
  releaseStreamAbortController: (instance: AbortController) => void;
  /** User Stop button or logout — aborts in-flight stream; UI handled via ``handleChatStreamFailure``. */
  abortChatStreamFromUser: () => void;
  /** Cancel backend agent session — kills running tasks and subprocesses. */
  cancelBackendSession: (sessionId: string) => Promise<void>;
  /** Whether the last stream was stopped by the user (supports "continue" flow). */
  lastStopWasUserInitiated: boolean;
  /** Terminal reason from the last agent turn (populated from ``assistant_complete`` SSE). */
  lastTerminalReason: string | null;
  /** Checkpoint id from the last agent turn (enables durable resume). */
  lastCheckpointId: string | null;

  getCurrentMessages: () => Message[];
  getCurrentSession: () => ChatSession | null;

  /** GET /chat/sessions/:id — refresh pins (and title/count) for one session. */
  fetchSessionDetail: (sessionId: string) => Promise<void>;
  setSessionTodos: (sessionId: string, todos: TaskProgressStep[]) => void;
  upsertSessionTodoFromProgress: (sessionId: string, step: TaskProgressStep) => void;
  /** Persist a manual todo status change (Cursor-style click cycle). */
  patchSessionTodoStatus: (
    sessionId: string,
    taskId: string,
    status: TaskProgressStep['status'],
  ) => Promise<void>;
  /** Per-session todo panel: pinned to chat top + user dismissed state. */
  sessionTodoUi: Record<string, SessionTodoUiState>;
  setSessionTodoPinned: (sessionId: string, pinned: boolean) => void;
  dismissSessionTodoPanel: (sessionId: string) => void;
  /** Replace ordered pin list; persists via metadata_patch. */
  setPinnedMessageIds: (sessionId: string, messageIds: string[]) => Promise<void>;
  /** Toggle one message id in the pin list (optimistic + PATCH). */
  togglePinMessage: (sessionId: string, messageId: string) => Promise<void>;

  /**
   * Ephemeral: coding projects started via ``coding_project_run`` in a thread
   * (not persisted) — used to stop dev servers when leaving the conversation.
   */
  codingProjectIdsBySession: Record<string, string[]>;
  registerCodingProjectForSession: (sessionId: string, projectId: string) => void;
  stopCodingProjectsForSession: (sessionId: string | null | undefined) => Promise<void>;
}

interface SessionResponse {
  id: string;
  name: string;
  project_id?: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
  pinned_message_ids?: string[];
  todos?: Array<{
    id: string;
    content: string;
    status: TaskProgressStep['status'];
    order?: number;
  }>;
}

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_prev: boolean;
}

const TASK_STATUS_RANK: Record<TaskProgressStep['status'], number> = {
  pending: 0,
  in_progress: 1,
  completed: 2,
  failed: 2,
  cancelled: 2,
};

/** Skip server fetch while the HTTP stream for this session is still active. */
function shouldSkipFetchMessages(sessionId: string, state: ChatStore): boolean {
  return isChatStreamBusyForSession(sessionId, state);
}

/** Keeps first occurrence of each message id (chronological merge order preserved). */
export function dedupeMessagesByIdPreserveOrder(messages: Message[]): Message[] {
  const seen = new Set<string>();
  const out: Message[] = [];
  for (const m of messages) {
    if (seen.has(m.id)) continue;
    seen.add(m.id);
    out.push(m);
  }
  return out;
}

function mapApiTodosToSteps(
  todos: SessionResponse['todos'],
): TaskProgressStep[] | undefined {
  if (!Array.isArray(todos) || todos.length === 0) return undefined;
  return todos
    .map((item, index) => ({
      taskId: String(item.id),
      label: String(item.content || item.id),
      status: item.status,
      order: item.order ?? index,
    }))
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
}

const TODO_WRITE_TOOL_NAMES = new Set([
  'todo_write',
  'todo',
  'todo_create',
  'update_todo',
  'create_todo',
]);

function findLatestTodoAnchorMessage(messages: Message[]): Message | undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (!m || m.role !== 'assistant') continue;
    if (m.taskProgress?.length) return m;
    if (m.toolCalls?.some((tc) => TODO_WRITE_TOOL_NAMES.has(tc.name))) return m;
  }
  return undefined;
}

function resolveSessionTodoBaseline(
  sessionId: string,
  state: Pick<ChatStore, 'sessions' | 'messages'>,
): TaskProgressStep[] {
  const fromSession = state.sessions.find((s) => s.id === sessionId)?.todos;
  if (fromSession?.length) return fromSession;
  return findLatestTodoAnchorMessage(state.messages[sessionId] ?? [])?.taskProgress ?? [];
}

function applyTodoStatusUpdate(
  todos: TaskProgressStep[],
  taskId: string,
  status: TaskProgressStep['status'],
): TaskProgressStep[] {
  return todos.map((item) => {
    if (item.taskId === taskId) {
      return { ...item, status };
    }
    if (status === 'in_progress' && item.status === 'in_progress') {
      return { ...item, status: 'pending' as const };
    }
    return item;
  });
}

function syncTodoAnchorMessageProgress(
  sessionId: string,
  todos: TaskProgressStep[],
  set: (partial: Partial<ChatStore> | ((state: ChatStore) => Partial<ChatStore>)) => void,
  get: () => ChatStore,
) {
  const anchor = findLatestTodoAnchorMessage(get().messages[sessionId] ?? []);
  if (!anchor) return;
  set((state) => ({
    messages: {
      ...state.messages,
      [sessionId]: (state.messages[sessionId] || []).map((m) =>
        m.id === anchor.id ? { ...m, taskProgress: todos } : m,
      ),
    },
  }));
}

function mapSession(s: SessionResponse): ChatSession {
  const pins = s.pinned_message_ids;
  const base: ChatSession = {
    id: s.id,
    title: s.name || i18n.t('chat.defaultSessionName'),
    createdAt: s.created_at,
    updatedAt: s.updated_at,
    messageCount: s.message_count,
    projectId: s.project_id ?? null,
    pinnedMessageIds: Array.isArray(pins) ? pins.map(String) : [],
  };
  const todos = mapApiTodosToSteps(s.todos);
  if (todos?.length) {
    base.todos = todos;
  }
  return base;
}

function projectIdForSession(sessionId: string): string | null {
  const session = useChatStore.getState().sessions.find((s) => s.id === sessionId);
  return session?.projectId ?? null;
}

/** Project unlock header for session-scoped chat API calls. */
export function getSessionProjectHeaders(sessionId: string): Record<string, string> | undefined {
  return getChatProjectHeaders(projectIdForSession(sessionId));
}

/** False when the session belongs to a password-protected project without a stored unlock token. */
export function isSessionProjectUnlocked(sessionId: string): boolean {
  const projectId = projectIdForSession(sessionId);
  if (!projectId) return true;
  return useChatProjectStore.getState().isProjectUnlocked(projectId);
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessions: [],
      currentSessionId: null,
      messages: {},
      messagePages: {},
      messagesLoadingSessionId: null,
      activeStreamSessionId: null,
      isLoading: false,
      isStreaming: false,
      error: null,
      synced: false,
      chatSessionsReconciled: false,
      pendingUserInput: null,
      streamAbortController: null,
      lastStopWasUserInitiated: false,
      lastTerminalReason: null,
      lastCheckpointId: null,
      nestedAgentPreviewBySession: {},
      codingProjectIdsBySession: {},
      sessionTodoUi: {},

      registerCodingProjectForSession: (sessionId, projectId) => {
        const id = projectId.trim();
        if (!sessionId || !id) return;
        set((state) => {
          const cur = state.codingProjectIdsBySession[sessionId] ?? [];
          if (cur.includes(id)) return state;
          return {
            codingProjectIdsBySession: {
              ...state.codingProjectIdsBySession,
              [sessionId]: [...cur, id],
            },
          };
        });
      },

      stopCodingProjectsForSession: async (sessionId) => {
        if (!sessionId) return;
        const ids = get().codingProjectIdsBySession[sessionId] ?? [];
        set((s) => {
          const next = { ...s.codingProjectIdsBySession };
          delete next[sessionId];
          return { codingProjectIdsBySession: next };
        });
        for (const projectId of ids) {
          try {
            await apiClient.post(`/coding-projects/${projectId}/stop`);
          } catch {
            /* best-effort */
          }
        }
      },

      setNestedAgentPreview: (sessionId, preview) => {
        set((state) => ({
          nestedAgentPreviewBySession: {
            ...state.nestedAgentPreviewBySession,
            [sessionId]: preview,
          },
        }));
      },

      fetchSessions: async (projectId) => {
        try {
          const params: Record<string, string | number> = { page: 1, page_size: 100 };
          if (projectId) params.project_id = projectId;
          const res = await apiClient.get<PaginatedResponse<SessionResponse>>(
            '/chat/sessions',
            params,
            { headers: getChatProjectHeaders(projectId) },
          );
          const sessions = res.items.map(mapSession);
          set((state) => ({
            sessions,
            synced: true,
            currentSessionId: state.currentSessionId && sessions.some((s) => s.id === state.currentSessionId)
              ? state.currentSessionId
              : sessions[0]?.id ?? null,
          }));
        } catch {
          // Fall back to local sessions if backend is unreachable
        } finally {
          set({ chatSessionsReconciled: true });
        }
      },

      createSession: async (title, projectIdArg) => {
        const activeProjectId =
          projectIdArg !== undefined
            ? projectIdArg
            : useChatProjectStore.getState().currentProjectId;
        const tempId = generateId();
        const now = new Date().toISOString();
        const tempSession: ChatSession = {
          id: tempId,
          title: title || i18n.t('chat.defaultSessionName'),
          createdAt: now,
          updatedAt: now,
          messageCount: 0,
          projectId: activeProjectId ?? null,
          pinnedMessageIds: [],
          isPending: true,
        };

        set((state) => ({
          sessions: [tempSession, ...state.sessions],
          currentSessionId: tempId,
          messages: { ...state.messages, [tempId]: [] },
          sessionTodoUi: {
            ...state.sessionTodoUi,
            [tempId]: { pinned: false, dismissed: false },
          },
          pendingUserInput: null,
        }));
        useExecutionSessionStore.getState().clearSession(tempId);

        try {
          const res = await apiClient.post<SessionResponse>('/chat/sessions', {
            name: title || i18n.t('chat.defaultSessionName'),
            project_id: activeProjectId || undefined,
          }, { headers: getChatProjectHeaders(activeProjectId) });
          const session = mapSession(res);
          delete session.todos;

          set((state) => {
            const newMessages = { ...state.messages };
            const tempMessages = newMessages[tempId] || [];
            delete newMessages[tempId];
            newMessages[session.id] = tempMessages;

            const nextTodoUi = { ...state.sessionTodoUi };
            delete nextTodoUi[tempId];
            nextTodoUi[session.id] = { pinned: false, dismissed: false };

            return {
              sessions: state.sessions.map((s) => (s.id === tempId ? session : s)),
              currentSessionId: state.currentSessionId === tempId ? session.id : state.currentSessionId,
              messages: newMessages,
              sessionTodoUi: nextTodoUi,
              pendingUserInput:
                state.pendingUserInput &&
                (state.pendingUserInput.sessionId === tempId ||
                  state.pendingUserInput.sessionId === session.id)
                  ? null
                  : state.pendingUserInput,
            };
          });
          useExecutionSessionStore.getState().remapSession(tempId, session.id);

          return session.id;
        } catch {
          return tempId;
        }
      },

      deleteSession: async (id) => {
        const wasCurrentSession = get().currentSessionId === id;
        set((state) => {
          const newSessions = state.sessions.filter((s) => s.id !== id);
          const newMessages = { ...state.messages };
          const newMessagePages = { ...state.messagePages };
          delete newMessages[id];
          delete newMessagePages[id];
          const clearPending =
            state.pendingUserInput?.sessionId === id ? null : state.pendingUserInput;
          return {
            sessions: newSessions,
            currentSessionId: state.currentSessionId === id
              ? newSessions[0]?.id ?? null
              : state.currentSessionId,
            messages: newMessages,
            messagePages: newMessagePages,
            pendingUserInput: clearPending,
          };
        });

        // Reset workspace-side state when deleting the active session.
        if (wasCurrentSession) {
          useChatDraftStore.getState().clearPendingInsert();
          useChatDraftStore.getState().clearFolderContext();
          useLayoutStore.setState({ workspaceTab: 'files' });
          useArtifactStore.getState().closeArtifact();
          useArtifactStore.setState({ openTabIds: [], activeTabId: null });
        }
        useArtifactStore.getState().clearSessionArtifacts(id);
        useGenUiStore.getState().clearForSession(id);
        useExecutionSessionStore.getState().clearSession(id);

        try {
          await apiClient.delete(`/chat/sessions/${id}`, {
            headers: getChatProjectHeaders(projectIdForSession(id)),
          });
        } catch {
          // Session already removed from local state
        }
      },

      dropStaleSession: (id) => {
        const wasCurrentSession = get().currentSessionId === id;
        set((state) => {
          const newSessions = state.sessions.filter((s) => s.id !== id);
          const newMessages = { ...state.messages };
          const newMessagePages = { ...state.messagePages };
          delete newMessages[id];
          delete newMessagePages[id];
          const clearPending =
            state.pendingUserInput?.sessionId === id ? null : state.pendingUserInput;
          return {
            sessions: newSessions,
            currentSessionId: state.currentSessionId === id
              ? newSessions[0]?.id ?? null
              : state.currentSessionId,
            messages: newMessages,
            messagePages: newMessagePages,
            pendingUserInput: clearPending,
          };
        });

        if (wasCurrentSession) {
          useChatDraftStore.getState().clearPendingInsert();
          useChatDraftStore.getState().clearFolderContext();
          useLayoutStore.setState({ workspaceTab: 'files' });
          useArtifactStore.getState().closeArtifact();
          useArtifactStore.setState({ openTabIds: [], activeTabId: null });
        }
        useArtifactStore.getState().clearSessionArtifacts(id);
        useGenUiStore.getState().clearForSession(id);
      },

      selectSession: (id) => {
        if (!isUuid(id)) return;
        set((state) => ({
          currentSessionId: id,
          pendingUserInput:
            state.pendingUserInput && state.pendingUserInput.sessionId !== id
              ? null
              : state.pendingUserInput,
        }));
        // Prompt-preview cache must not reuse another thread’s snapshot when switching history.
        void queryClient.invalidateQueries({ queryKey: ['prompt-preview', id] });
        // Always sync from server when opening a thread. A cached `[]` is truthy in JS, so the old
        // `if (!messages[id])` guard skipped fetch after clearMessages / failed loads and left stale UI.
        void get().fetchMessages(id);
        void get().fetchSessionDetail(id);
      },

      updateSessionTitle: (id, title) => {
        set((state) => ({
          sessions: state.sessions.map((s) =>
            s.id === id ? { ...s, title, updatedAt: new Date().toISOString() } : s
          ),
        }));
        apiClient.patch(
          `/chat/sessions/${id}`,
          { name: title },
          { headers: getChatProjectHeaders(projectIdForSession(id)) },
        ).catch(() => {});
      },

      fetchSessionDetail: async (sessionId) => {
        if (!isUuid(sessionId)) return;
        try {
          const res = await apiClient.get<SessionResponse>(
            `/chat/sessions/${sessionId}`,
            undefined,
            { headers: getChatProjectHeaders(projectIdForSession(sessionId)) },
          );
          const mapped = mapSession(res);
          set((state) => ({
            sessions: state.sessions.map((s) => {
              if (s.id !== sessionId) return s;
              const streaming = isChatStreamBusyForSession(sessionId, state);
              const next: ChatSession = { ...s, ...mapped };
              if (mapped.todos?.length) {
                next.todos = mapped.todos;
              } else if (Array.isArray(res.todos) && !streaming) {
                delete next.todos;
              } else {
                next.todos = s.todos;
              }
              return next;
            }),
          }));
        } catch (e) {
          if (e instanceof HttpError && e.status === 404) {
            get().dropStaleSession(sessionId);
          }
        }
      },

      setSessionTodos: (sessionId, todos) => {
        set((state) => ({
          sessions: state.sessions.map((s) =>
            s.id === sessionId ? { ...s, todos: todos.length ? todos : undefined } : s,
          ),
        }));
        if (todos.length) {
          syncTodoAnchorMessageProgress(sessionId, todos, set, get);
        }
      },

      setSessionTodoPinned: (sessionId, pinned) => {
        set((state) => ({
          sessionTodoUi: {
            ...state.sessionTodoUi,
            [sessionId]: {
              pinned,
              dismissed: pinned ? false : (state.sessionTodoUi[sessionId]?.dismissed ?? false),
            },
          },
        }));
      },

      dismissSessionTodoPanel: (sessionId) => {
        set((state) => ({
          sessionTodoUi: {
            ...state.sessionTodoUi,
            [sessionId]: {
              pinned: state.sessionTodoUi[sessionId]?.pinned ?? true,
              dismissed: true,
            },
          },
        }));
      },

      upsertSessionTodoFromProgress: (sessionId, step) => {
        set((state) => ({
          sessions: state.sessions.map((s) => {
            if (s.id !== sessionId) return s;
            const existing = s.todos ?? [];
            const idx = existing.findIndex((item) => item.taskId === step.taskId);
            if (idx === -1) {
              return { ...s, todos: [...existing, step] };
            }
            const prev = existing[idx];
            if (!prev) return s;
            const prevRank = TASK_STATUS_RANK[prev.status];
            const nextRank = TASK_STATUS_RANK[step.status];
            if (nextRank < prevRank) return s;
            if (
              nextRank === prevRank &&
              prev.status === step.status &&
              prev.label === step.label &&
              prev.progress === step.progress &&
              prev.order === step.order
            ) {
              return s;
            }
            const next = [...existing];
            next[idx] = {
              ...prev,
              ...step,
              order: step.order ?? prev.order,
            };
            return { ...s, todos: next };
          }),
        }));
        const todos = get().sessions.find((s) => s.id === sessionId)?.todos;
        if (todos?.length) {
          syncTodoAnchorMessageProgress(sessionId, todos, set, get);
        }
      },

      patchSessionTodoStatus: async (sessionId, taskId, status) => {
        if (!isUuid(sessionId)) return;
        const state = get();
        const prev = resolveSessionTodoBaseline(sessionId, state);
        if (!prev.length) return;

        const optimistic = applyTodoStatusUpdate(prev, taskId, status);
        get().setSessionTodos(sessionId, optimistic);
        syncTodoAnchorMessageProgress(sessionId, optimistic, set, get);

        try {
          const res = await apiClient.patch<SessionResponse>(
            `/chat/sessions/${sessionId}/todos/${encodeURIComponent(taskId)}`,
            { status },
            { headers: getChatProjectHeaders(projectIdForSession(sessionId)) },
          );
          const mapped = mapApiTodosToSteps(res.todos);
          if (mapped?.length) {
            get().setSessionTodos(sessionId, mapped);
            syncTodoAnchorMessageProgress(sessionId, mapped, set, get);
          }
        } catch {
          get().setSessionTodos(sessionId, prev);
          syncTodoAnchorMessageProgress(sessionId, prev, set, get);
        }
      },

      setPinnedMessageIds: async (sessionId, messageIds) => {
        const prev = get().sessions.find((s) => s.id === sessionId);
        const previousPins = prev?.pinnedMessageIds ?? [];
        set((state) => ({
          sessions: state.sessions.map((s) =>
            s.id === sessionId ? { ...s, pinnedMessageIds: messageIds } : s,
          ),
        }));
        try {
          const res = await apiClient.patch<SessionResponse>(
            `/chat/sessions/${sessionId}`,
            {
              metadata_patch: { pinned_message_ids: messageIds },
            },
            { headers: getChatProjectHeaders(projectIdForSession(sessionId)) },
          );
          const mapped = mapSession(res);
          set((state) => ({
            sessions: state.sessions.map((s) => (s.id === sessionId ? { ...s, ...mapped } : s)),
          }));
        } catch {
          set((state) => ({
            sessions: state.sessions.map((s) =>
              s.id === sessionId ? { ...s, pinnedMessageIds: previousPins } : s,
            ),
          }));
        }
      },

      togglePinMessage: async (sessionId, messageId) => {
        const sess = get().sessions.find((s) => s.id === sessionId);
        const cur = sess?.pinnedMessageIds ?? [];
        const has = cur.includes(messageId);
        const next = has ? cur.filter((id) => id !== messageId) : [...cur, messageId];
        await get().setPinnedMessageIds(sessionId, next);
      },

      fetchMessages: async (sessionId) => {
        if (!isUuid(sessionId)) return;
        const before = get();
        if (shouldSkipFetchMessages(sessionId, before)) {
          return;
        }

        const seq = ++messagesFetchSeq;
        set({ messagesLoadingSessionId: sessionId });
        try {
          const res = await apiClient.get<PaginatedResponse<MessageResponse>>(
            `/chat/sessions/${sessionId}/messages`,
            { page: 1, page_size: CHAT_MESSAGES_PAGE_SIZE, order: 'desc' },
            { headers: getChatProjectHeaders(projectIdForSession(sessionId)) },
          );
          if (seq !== messagesFetchSeq) return;

          const chronologicalRows = [...res.items].reverse();
          const normalized = normalizeMessageList(chronologicalRows);
          const enriched = await enrichMessagesWithSessionAttachments(sessionId, normalized);
          if (seq !== messagesFetchSeq) return;

          const dedupedEnriched = ensureChronologicalMessages(
            dedupeMessagesByIdPreserveOrder(enriched),
          );

          let appliedFullMerge = false;
          set((state) => {
            if (shouldSkipFetchMessages(sessionId, state)) {
              return {
                messagesLoadingSessionId:
                  state.messagesLoadingSessionId === sessionId
                    ? null
                    : state.messagesLoadingSessionId,
              };
            }
            appliedFullMerge = true;
            const msgIds = new Set(dedupedEnriched.map((m) => m.id));
            const sess = state.sessions.find((s) => s.id === sessionId);
            let sessions = state.sessions;
            const pinList = sess?.pinnedMessageIds ?? [];
            if (pinList.length) {
              const nextPins = pinList.filter((id) => msgIds.has(id));
              if (nextPins.length !== pinList.length) {
                sessions = state.sessions.map((s) =>
                  s.id === sessionId ? { ...s, pinnedMessageIds: nextPins } : s,
                );
                void apiClient
                  .patch(`/chat/sessions/${sessionId}`, {
                    metadata_patch: { pinned_message_ids: nextPins },
                  }, {
                    headers: getChatProjectHeaders(projectIdForSession(sessionId)),
                  })
                  .catch(() => {});
              }
            }
            return {
              messages: {
                ...state.messages,
                [sessionId]: dedupedEnriched,
              },
              messagePages: {
                ...state.messagePages,
                [sessionId]: {
                  hasOlder: res.has_next,
                  nextOlderPage: 2,
                  isLoadingOlder: false,
                },
              },
              messagesLoadingSessionId:
                state.messagesLoadingSessionId === sessionId
                  ? null
                  : state.messagesLoadingSessionId,
              sessions,
            };
          });
          if (appliedFullMerge) {
            hydrateGenUiFromMessages(sessionId, dedupedEnriched);
            void hydrateSessionCanvasArtifacts(sessionId);
          }
        } catch (e) {
          if (e instanceof HttpError && e.status === 404) {
            get().dropStaleSession(sessionId);
          }
          set((state) => ({
            messagesLoadingSessionId:
              state.messagesLoadingSessionId === sessionId
                ? null
                : state.messagesLoadingSessionId,
          }));
          // Keep existing local messages on failure (except 404 — stale thread removed above)
        }
      },

      fetchOlderMessages: async (sessionId) => {
        const pageState = get().messagePages[sessionId];
        if (!pageState?.hasOlder || pageState.isLoadingOlder) return;

        set((state) => ({
          messagePages: {
            ...state.messagePages,
            [sessionId]: { ...pageState, isLoadingOlder: true },
          },
        }));

        try {
          const res = await apiClient.get<PaginatedResponse<MessageResponse>>(
            `/chat/sessions/${sessionId}/messages`,
            {
              page: pageState.nextOlderPage,
              page_size: CHAT_MESSAGES_PAGE_SIZE,
              order: 'desc',
            },
            { headers: getChatProjectHeaders(projectIdForSession(sessionId)) },
          );
          const olderMessages = normalizeMessageList([...res.items].reverse());
          const existingSnapshot = get().messages[sessionId] ?? [];
          const existingIds = new Set(existingSnapshot.map((m) => m.id));
          const dedupedOlder = olderMessages.filter((m) => !existingIds.has(m.id));
          const mergedForEnrich = [...dedupedOlder, ...existingSnapshot];
          const enrichedMerged = await enrichMessagesWithSessionAttachments(
            sessionId,
            mergedForEnrich,
          );
          const dedupedMerged = ensureChronologicalMessages(
            dedupeMessagesByIdPreserveOrder(enrichedMerged),
          );
          set((state) => ({
            messages: {
              ...state.messages,
              [sessionId]: dedupedMerged,
            },
            messagePages: {
              ...state.messagePages,
              [sessionId]: {
                hasOlder: res.has_next,
                nextOlderPage: pageState.nextOlderPage + 1,
                isLoadingOlder: false,
              },
            },
          }));
          const merged = get().messages[sessionId] ?? [];
          hydrateGenUiFromMessages(sessionId, merged);
          void hydrateSessionCanvasArtifacts(sessionId);
        } catch {
          set((state) => ({
            messagePages: {
              ...state.messagePages,
              [sessionId]: { ...pageState, isLoadingOlder: false },
            },
          }));
        }
      },

      addMessage: (sessionId, message) => {
        set((state) => {
          const sessionMessages = state.messages[sessionId] || [];
          const updatedMessages = [...sessionMessages, message];
          return {
            messages: { ...state.messages, [sessionId]: updatedMessages },
            sessions: state.sessions.map((s) =>
              s.id === sessionId
                ? {
                    ...s,
                    messageCount: updatedMessages.length,
                    updatedAt: new Date().toISOString(),
                    preview: message.role === 'user' ? message.content.slice(0, 50) : s.preview,
                  }
                : s
            ),
          };
        });
      },

      insertSteerMessage: (sessionId, message) => {
        set((state) => {
          const sessionMessages = state.messages[sessionId] || [];
          if (sessionMessages.some((m) => m.id === message.id)) {
            return state;
          }
          let insertIdx = sessionMessages.length;
          for (let i = sessionMessages.length - 1; i >= 0; i--) {
            if (sessionMessages[i]?.role === 'assistant') {
              insertIdx = i;
              break;
            }
          }
          const updatedMessages = [
            ...sessionMessages.slice(0, insertIdx),
            message,
            ...sessionMessages.slice(insertIdx),
          ];
          return {
            messages: { ...state.messages, [sessionId]: updatedMessages },
            sessions: state.sessions.map((s) =>
              s.id === sessionId
                ? {
                    ...s,
                    messageCount: updatedMessages.length,
                    updatedAt: new Date().toISOString(),
                    preview: message.content.slice(0, 50),
                  }
                : s
            ),
          };
        });
      },

      updateMessage: (sessionId, messageId, updates) => {
        set((state) => ({
          messages: {
            ...state.messages,
            [sessionId]: (state.messages[sessionId] || []).map((m) =>
              m.id === messageId ? { ...m, ...updates } : m
            ),
          },
        }));
      },

      appendToMessage: (sessionId, messageId, content) => {
        set((state) => ({
          messages: {
            ...state.messages,
            [sessionId]: (state.messages[sessionId] || []).map((m) =>
              m.id === messageId ? { ...m, content: m.content + content } : m
            ),
          },
        }));
      },

      updateToolCall: (sessionId, messageId, toolCallId, updates) => {
        set((state) => ({
          messages: {
            ...state.messages,
            [sessionId]: (state.messages[sessionId] || []).map((m) => {
              if (m.id !== messageId) return m;
              return {
                ...m,
                toolCalls: m.toolCalls?.map((tc) =>
                  tc.id === toolCallId ? { ...tc, ...updates } : tc
                ),
              };
            }),
          },
        }));
      },

      finalizeToolCalls: (sessionId, messageId, terminalStatus = 'success') => {
        set((state) => ({
          messages: {
            ...state.messages,
            [sessionId]: (state.messages[sessionId] || []).map((m) => {
              if (m.id !== messageId || !m.toolCalls?.length) return m;
              return {
                ...m,
                toolCalls: m.toolCalls.map((tc) =>
                  tc.status === 'pending' || tc.status === 'running'
                    ? { ...tc, status: terminalStatus }
                    : tc
                ),
              };
            }),
          },
        }));
      },

      upsertTaskProgress: (sessionId, messageId, step) => {
        set((state) => ({
          messages: {
            ...state.messages,
            [sessionId]: (state.messages[sessionId] || []).map((m) => {
              if (m.id !== messageId) return m;
              const existing = m.taskProgress || [];
              const idx = existing.findIndex((item) => item.taskId === step.taskId);
              if (idx === -1) {
                return { ...m, taskProgress: [...existing, step] };
              }
              const prev = existing[idx];
              if (!prev) {
                return m;
              }
              const prevRank = TASK_STATUS_RANK[prev.status];
              const nextRank = TASK_STATUS_RANK[step.status];
              if (nextRank < prevRank) {
                return m;
              }
              if (
                nextRank === prevRank &&
                prev.label === step.label &&
                prev.progress === step.progress &&
                prev.order === step.order
              ) {
                return m;
              }
              const next = [...existing];
              next[idx] = {
                ...prev,
                ...step,
                order: step.order ?? prev.order,
              };
              return { ...m, taskProgress: next };
            }),
          },
        }));
      },

      finalizeTaskProgress: (sessionId, messageId, terminalStatus = 'completed') => {
        set((state) => ({
          messages: {
            ...state.messages,
            [sessionId]: (state.messages[sessionId] || []).map((m) => {
              if (m.id !== messageId || !m.taskProgress?.length) return m;
              return {
                ...m,
                taskProgress: m.taskProgress.map((step) =>
                  step.status === 'pending' || step.status === 'in_progress'
                    ? { ...step, status: terminalStatus }
                    : step
                ),
              };
            }),
          },
        }));
      },

      updateWorkflowStepRun: (sessionId, messageId, stepId, partial) => {
        set((state) => ({
          messages: {
            ...state.messages,
            [sessionId]: (state.messages[sessionId] || []).map((m) => {
              if (m.id !== messageId || !m.workflow) return m;
              const prev = m.workflow.stepRuns[stepId] ?? { status: 'idle' as const };
              return {
                ...m,
                workflow: {
                  ...m.workflow,
                  stepRuns: {
                    ...m.workflow.stepRuns,
                    [stepId]: { ...prev, ...partial },
                  },
                },
              };
            }),
          },
        }));
      },

      clearMessages: (sessionId) => {
        set((state) => ({
          messages: { ...state.messages, [sessionId]: [] },
          messagePages: {
            ...state.messagePages,
            [sessionId]: { hasOlder: false, nextOlderPage: 1, isLoadingOlder: false },
          },
          sessions: state.sessions.map((s) =>
            s.id === sessionId ? { ...s, messageCount: 0, preview: undefined } : s
          ),
          pendingUserInput:
            state.pendingUserInput?.sessionId === sessionId ? null : state.pendingUserInput,
          nestedAgentPreviewBySession: {
            ...state.nestedAgentPreviewBySession,
            [sessionId]: null,
          },
        }));
      },

      truncateAfterMessageId: (sessionId, messageId) => {
        const state = get();
        const list = state.messages[sessionId] || [];
        const idx = list.findIndex((m) => m.id === messageId);
        if (idx === -1) return false;
        const next = list.slice(0, idx + 1);
        let lastUserPreview: string | undefined;
        for (let i = next.length - 1; i >= 0; i--) {
          const m = next[i];
          if (m?.role === 'user') {
            lastUserPreview = m.content?.slice(0, 50);
            break;
          }
        }
        set((s) => ({
          messages: { ...s.messages, [sessionId]: next },
          sessions: s.sessions.map((sess) =>
            sess.id === sessionId
              ? {
                  ...sess,
                  messageCount: next.length,
                  updatedAt: new Date().toISOString(),
                  preview: lastUserPreview ?? sess.preview,
                }
              : sess
          ),
        }));
        return true;
      },

      remapStreamPersistedIds: (sessionId, mapping) => {
        const { clientUserId, serverUserId, clientAssistantId, serverAssistantId } = mapping;
        const userPair =
          serverUserId && serverUserId !== clientUserId
            ? ([clientUserId, serverUserId] as const)
            : null;
        const asstPair =
          serverAssistantId && serverAssistantId !== clientAssistantId
            ? ([clientAssistantId, serverAssistantId] as const)
            : null;
        if (!userPair && !asstPair) return;

        set((state) => {
          let list = [...(state.messages[sessionId] || [])];
          const applyPair = (oldId: string, newId: string) => {
            list = list.map((m) => (m.id === oldId ? { ...m, id: newId } : m));
          };
          if (userPair) applyPair(userPair[0], userPair[1]);
          if (asstPair) applyPair(asstPair[0], asstPair[1]);

          let sessions = state.sessions;
          const remapPins = (oldId: string, newId: string) => {
            sessions = sessions.map((s) => {
              if (s.id !== sessionId) return s;
              const pins = s.pinnedMessageIds ?? [];
              if (!pins.includes(oldId)) return s;
              return {
                ...s,
                pinnedMessageIds: pins.map((p) => (p === oldId ? newId : p)),
              };
            });
          };
          if (userPair) remapPins(userPair[0], userPair[1]);
          if (asstPair) remapPins(asstPair[0], asstPair[1]);

          let pendingUserInput = state.pendingUserInput;
          if (
            pendingUserInput?.sessionId === sessionId &&
            asstPair &&
            pendingUserInput.assistantMsgId === asstPair[0]
          ) {
            pendingUserInput = { ...pendingUserInput, assistantMsgId: asstPair[1] };
          }

          return {
            messages: { ...state.messages, [sessionId]: list },
            pendingUserInput,
            sessions,
          };
        });

        const genUi = useGenUiStore.getState();
        const artifacts = useArtifactStore.getState();
        if (userPair) {
          genUi.remapMessageId(sessionId, userPair[0], userPair[1]);
          artifacts.remapArtifactsMessageId(sessionId, userPair[0], userPair[1]);
        }
        if (asstPair) {
          genUi.remapMessageId(sessionId, asstPair[0], asstPair[1]);
          artifacts.remapArtifactsMessageId(sessionId, asstPair[0], asstPair[1]);
        }
      },

      setLoading: (isLoading) => set({ isLoading }),
      setStreaming: (isStreaming) => set({ isStreaming }),
      beginChatStreamSession: (sessionId) =>
        set({
          activeStreamSessionId: sessionId,
          isLoading: true,
          isStreaming: true,
        }),
      releaseChatStreamSession: (sessionId) => {
        const s = get();
        if (s.activeStreamSessionId !== sessionId) return;
        set({
          activeStreamSessionId: null,
          isLoading: false,
          isStreaming: false,
        });
      },
      releaseChatStreamSessionAndResync: (sessionId) => {
        get().releaseChatStreamSession(sessionId);
        void get().fetchMessages(sessionId);
        void get().fetchSessionDetail(sessionId);
      },
      abortActiveStreamUnlessSession: (sessionId) => {
        const s = get();
        if (
          s.streamAbortController &&
          s.activeStreamSessionId != null &&
          s.activeStreamSessionId !== sessionId
        ) {
          s.streamAbortController.abort();
        }
      },
      setError: (error) => set({ error }),
      setPendingUserInput: (payload) => set({ pendingUserInput: payload }),
      clearPendingUserInput: () => set({ pendingUserInput: null }),

      setStreamAbortController: (controller) => set({ streamAbortController: controller }),
      releaseStreamAbortController: (instance) => {
        const cur = get().streamAbortController;
        if (cur === instance) set({ streamAbortController: null });
      },
      abortChatStreamFromUser: () => {
        get().streamAbortController?.abort();
        set({ lastStopWasUserInitiated: true });

        const sessionId = get().currentSessionId;
        if (sessionId) {
          void get().cancelBackendSession(sessionId);
        }
      },

      cancelBackendSession: async (sessionId: string) => {
        try {
          await apiClient.post(
            `/chat/sessions/${sessionId}/cancel`,
            undefined,
            { headers: getChatProjectHeaders(projectIdForSession(sessionId)) },
          );
        } catch {
          // Best-effort; the SSE abort already closed the client connection
        }
      },

      getCurrentMessages: () => {
        const state = get();
        if (!state.currentSessionId) return [];
        return state.messages[state.currentSessionId] || [];
      },

      getCurrentSession: () => {
        const state = get();
        if (!state.currentSessionId) return null;
        return state.sessions.find((s) => s.id === state.currentSessionId) || null;
      },
    }),
    {
      name: namespacedPersistName(CHAT_STORE_BASE),
      partialize: (state) => ({
        sessions: state.sessions.slice(0, 50),
        currentSessionId: state.currentSessionId,
      }),
      onRehydrateStorage: () => (state) => {
        if (state && state.currentSessionId && !isUuid(state.currentSessionId)) {
          state.currentSessionId = null;
        }
      },
    }
  )
);

/** True when this thread owns the in-flight chat stream (composer should block send). */
export function isChatStreamBusyForSession(
  sessionId: string | null | undefined,
  state: Pick<
    ChatStore,
    'activeStreamSessionId' | 'isLoading' | 'isStreaming'
  >,
): boolean {
  if (!sessionId) return false;
  return (
    state.activeStreamSessionId === sessionId &&
    (state.isLoading || state.isStreaming)
  );
}
