import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { TFunction } from 'i18next';
import type { ChatSession, Message } from '@/types/chat';
import { apiClient } from '@/api/client';
import { dedupeMessagesByIdPreserveOrder, useChatStore } from './chat';
import { applyChatStreamEvent } from '@/lib/chatStreamEvents';
import { useExecutionSessionStore } from './executionSession';

vi.mock('@/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  HttpError: class HttpError extends Error {
    readonly status: number;
    constructor(message: string, status: number) {
      super(message);
      this.name = 'HttpError';
      this.status = status;
    }
  },
}));

const SESSION_ID = '00000000-0000-4000-8000-000000000001';

const t = ((k: string) => k) as unknown as TFunction;

const session: ChatSession = {
  id: SESSION_ID,
  title: 'Session',
  createdAt: new Date(0).toISOString(),
  updatedAt: new Date(0).toISOString(),
  messageCount: 0,
  pinnedMessageIds: [],
};

const message = (id: string, role: Message['role'], content: string): Message => ({
  id,
  role,
  content,
  createdAt: new Date(0).toISOString(),
});

describe('dedupeMessagesByIdPreserveOrder', () => {
  it('keeps first occurrence and order', () => {
    const a = message('x', 'user', 'a');
    const b = message('y', 'assistant', 'b');
    expect(dedupeMessagesByIdPreserveOrder([a, b, { ...a, content: 'dup' }])).toEqual([a, b]);
  });
});

describe('useChatStore message operations', () => {
  beforeEach(() => {
    localStorage.clear();
    useChatStore.setState({
      sessions: [session],
      currentSessionId: session.id,
      messages: { [session.id]: [] },
      messagePages: {},
      messagesLoadingSessionId: null,
      activeStreamSessionId: null,
      isLoading: false,
      isStreaming: false,
      error: null,
      synced: false,
      pendingUserInput: null,
      streamAbortController: null,
    });
  });

  it('adds messages and updates session preview/count', () => {
    useChatStore.getState().addMessage(session.id, message('m1', 'user', 'hello world'));

    const state = useChatStore.getState();
    expect(state.messages[session.id]).toHaveLength(1);
    expect(state.sessions[0]?.messageCount).toBe(1);
    expect(state.sessions[0]?.preview).toBe('hello world');
  });

  it('updates tool call state in-place by id', () => {
    useChatStore.getState().addMessage(session.id, {
      ...message('a1', 'assistant', ''),
      toolCalls: [
        {
          id: 'tc1',
          name: 'project_read',
          arguments: { path: 'README.md' },
          status: 'running',
        },
      ],
    });

    useChatStore.getState().updateToolCall(session.id, 'a1', 'tc1', {
      status: 'success',
      result: 'content',
    });

    const toolCall = useChatStore.getState().messages[session.id]?.[0]?.toolCalls?.[0];
    expect(toolCall?.status).toBe('success');
    expect(toolCall?.result).toBe('content');
  });

  it('finalizes only unresolved tool calls', () => {
    useChatStore.getState().addMessage(session.id, {
      ...message('a1', 'assistant', ''),
      toolCalls: [
        {
          id: 'running',
          name: 'tool_argument_blob',
          arguments: {},
          status: 'running',
        },
        {
          id: 'pending',
          name: 'project_read',
          arguments: {},
          status: 'pending',
        },
        {
          id: 'awaiting',
          name: 'ask_user',
          arguments: {},
          status: 'awaiting_user',
        },
        {
          id: 'failed',
          name: 'project_write',
          arguments: {},
          status: 'error',
        },
      ],
    });

    useChatStore.getState().finalizeToolCalls(session.id, 'a1', 'success');

    const statuses = useChatStore.getState().messages[session.id]?.[0]?.toolCalls?.map((tc) => tc.status);
    expect(statuses).toEqual(['success', 'success', 'awaiting_user', 'error']);
  });

  it('truncates messages after a selected id', () => {
    const store = useChatStore.getState();
    store.addMessage(session.id, message('u1', 'user', 'first'));
    store.addMessage(session.id, message('a1', 'assistant', 'reply'));
    store.addMessage(session.id, message('u2', 'user', 'second'));

    expect(useChatStore.getState().truncateAfterMessageId(session.id, 'a1')).toBe(true);
    expect(useChatStore.getState().messages[session.id]?.map((m) => m.id)).toEqual([
      'u1',
      'a1',
    ]);
    expect(useChatStore.getState().sessions[0]?.messageCount).toBe(2);
  });
});

describe('fetchMessages stream guard', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    localStorage.clear();
    useChatStore.setState({
      sessions: [session],
      currentSessionId: session.id,
      messages: {
        [SESSION_ID]: [
          {
            id: 'asst-1',
            role: 'assistant',
            content: 'streaming…',
            createdAt: new Date().toISOString(),
            isStreaming: false,
          },
        ],
      },
      messagePages: {},
      messagesLoadingSessionId: null,
      activeStreamSessionId: SESSION_ID,
      isLoading: true,
      isStreaming: true,
      error: null,
      synced: false,
      pendingUserInput: null,
      streamAbortController: null,
    });
  });

  it('skips fetch while the HTTP stream is still active even if assistant isStreaming is false', async () => {
    await useChatStore.getState().fetchMessages(SESSION_ID);
    expect(apiClient.get).not.toHaveBeenCalled();
  });

  it('resyncs from the server after releaseChatStreamSessionAndResync', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      items: [
        {
          id: 'user-1',
          role: 'user',
          content: 'Q',
          created_at: '2026-04-28T00:00:00.000Z',
        },
        {
          id: 'asst-1',
          role: 'assistant',
          content: 'A',
          created_at: '2026-04-28T00:00:01.000Z',
        },
      ],
      total: 2,
      page: 1,
      page_size: 80,
      has_next: false,
      has_prev: false,
    });

    useChatStore.getState().releaseChatStreamSessionAndResync(SESSION_ID);
    await vi.waitFor(() => {
      expect(useChatStore.getState().messages[SESSION_ID]?.map((m) => m.id)).toEqual([
        'user-1',
        'asst-1',
      ]);
    });

    expect(useChatStore.getState().activeStreamSessionId).toBeNull();
  });

  it('setSessionTodos replaces session todo list', () => {
    useChatStore.getState().setSessionTodos(session.id, [
      { taskId: 't1', label: 'First', status: 'pending', order: 0 },
      { taskId: 't2', label: 'Second', status: 'in_progress', order: 1 },
    ]);
    expect(useChatStore.getState().sessions[0]?.todos).toHaveLength(2);
    expect(useChatStore.getState().sessions[0]?.todos?.[1]?.status).toBe('in_progress');
  });

  it('upsertSessionTodoFromProgress merges by taskId without regressing status', () => {
    useChatStore.getState().setSessionTodos(session.id, [
      { taskId: 't1', label: 'First', status: 'completed', order: 0 },
    ]);
    useChatStore.getState().upsertSessionTodoFromProgress(session.id, {
      taskId: 't1',
      label: 'First',
      status: 'pending',
      order: 0,
    });
    expect(useChatStore.getState().sessions[0]?.todos?.[0]?.status).toBe('completed');

    useChatStore.getState().upsertSessionTodoFromProgress(session.id, {
      taskId: 't2',
      label: 'Second',
      status: 'in_progress',
      order: 1,
    });
    expect(useChatStore.getState().sessions[0]?.todos).toHaveLength(2);
  });

  it('setSessionTodoPinned toggles pinned state and clears dismissed when pinning', () => {
    useChatStore.getState().dismissSessionTodoPanel(session.id);
    expect(useChatStore.getState().sessionTodoUi[session.id]?.dismissed).toBe(true);

    useChatStore.getState().setSessionTodoPinned(session.id, true);
    expect(useChatStore.getState().sessionTodoUi[session.id]).toEqual({
      pinned: true,
      dismissed: false,
    });

    useChatStore.getState().setSessionTodoPinned(session.id, false);
    expect(useChatStore.getState().sessionTodoUi[session.id]?.pinned).toBe(false);
  });

  it('dismissSessionTodoPanel hides pinned panel without unpinning', () => {
    useChatStore.getState().setSessionTodoPinned(session.id, true);
    useChatStore.getState().dismissSessionTodoPanel(session.id);
    expect(useChatStore.getState().sessionTodoUi[session.id]).toEqual({
      pinned: true,
      dismissed: true,
    });
  });

  it('patchSessionTodoStatus optimistically updates and calls API', async () => {
    useChatStore.getState().setSessionTodos(session.id, [
      { taskId: 't1', label: 'First', status: 'pending', order: 0 },
      { taskId: 't2', label: 'Second', status: 'in_progress', order: 1 },
    ]);

    vi.mocked(apiClient.patch).mockResolvedValue({
      id: session.id,
      name: session.title,
      message_count: 0,
      created_at: session.createdAt,
      updated_at: session.updatedAt,
      todos: [
        { id: 't1', content: 'First', status: 'in_progress', order: 0 },
        { id: 't2', content: 'Second', status: 'pending', order: 1 },
      ],
    });

    await useChatStore.getState().patchSessionTodoStatus(session.id, 't1', 'in_progress');

    expect(apiClient.patch).toHaveBeenCalledWith(
      `/chat/sessions/${session.id}/todos/t1`,
      { status: 'in_progress' },
      { headers: undefined },
    );
    expect(useChatStore.getState().sessions[0]?.todos?.[0]?.status).toBe('in_progress');
    expect(useChatStore.getState().sessions[0]?.todos?.[1]?.status).toBe('pending');
  });

  it('patchSessionTodoStatus seeds from anchor message taskProgress when session todos are empty', async () => {
    useChatStore.setState({
      messages: {
        [session.id]: [
          {
            id: 'a1',
            role: 'assistant',
            content: 'Planning',
            createdAt: session.createdAt,
            taskProgress: [
              { taskId: 't1', label: 'First', status: 'pending', order: 0 },
            ],
          },
        ],
      },
    });

    vi.mocked(apiClient.patch).mockResolvedValue({
      id: session.id,
      name: session.title,
      message_count: 1,
      created_at: session.createdAt,
      updated_at: session.updatedAt,
      todos: [{ id: 't1', content: 'First', status: 'in_progress', order: 0 }],
    });

    await useChatStore.getState().patchSessionTodoStatus(session.id, 't1', 'in_progress');

    expect(useChatStore.getState().sessions[0]?.todos?.[0]?.status).toBe('in_progress');
    expect(useChatStore.getState().messages[session.id]?.[0]?.taskProgress?.[0]?.status).toBe(
      'in_progress',
    );
  });

  it('createSession resets todo panel state and strips todos from the new session', async () => {
    useChatStore.getState().setSessionTodos(session.id, [
      { taskId: 't1', label: 'Old', status: 'pending', order: 0 },
    ]);
    useChatStore.getState().setSessionTodoPinned(session.id, true);

    const newId = '00000000-0000-4000-8000-000000000099';
    vi.mocked(apiClient.post).mockResolvedValue({
      id: newId,
      name: 'New Chat',
      message_count: 0,
      created_at: session.createdAt,
      updated_at: session.updatedAt,
      todos: [{ id: 't1', content: 'Should strip', status: 'pending', order: 0 }],
    });

    const createdId = await useChatStore.getState().createSession('New Chat');

    expect(createdId).toBe(newId);
    expect(useChatStore.getState().currentSessionId).toBe(newId);
    const created = useChatStore.getState().sessions.find((s) => s.id === newId);
    expect(created?.todos).toBeUndefined();
    expect(useChatStore.getState().sessionTodoUi[newId]).toEqual({
      pinned: false,
      dismissed: false,
    });
  });
});

describe('execution stream integration', () => {
  beforeEach(() => {
    useExecutionSessionStore.getState().clearSession(SESSION_ID);
  });

  it('applyChatStreamEvent records execution_started on session store', () => {
    applyChatStreamEvent(
      {
        type: 'execution_started',
        data: { run_id: 'run-xyz', session_id: SESSION_ID, scope: 'chat_turn' },
      },
      { sessionId: SESSION_ID, assistantMsgId: 'a1', userMessageId: 'u1', t },
    );

    const entry = useExecutionSessionStore.getState().bySession[SESSION_ID];
    expect(entry?.runId).toBe('run-xyz');
    expect(entry?.scope).toBe('chat_turn');
  });
});
