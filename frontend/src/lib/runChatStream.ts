import type { TFunction } from 'i18next';
import { getAccessToken } from '@/api/client';
import { applyChatStreamEvent, flushPendingContentBatch } from '@/lib/chatStreamEvents';
import { queryClient } from '@/lib/queryClient';
import { useChatStore } from '@/stores/chat';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';
const TITLE_POLL_INTERVAL_MS = 2500;
const TITLE_POLL_MAX_ATTEMPTS = 16;

function isPlaceholderSessionTitle(title: string | null | undefined): boolean {
  const value = (title ?? '').trim();
  if (!value) return true;
  const lower = value.toLowerCase();
  if (lower === 'new chat' || value === '新对话') return true;
  return /^(?:chat|new chat) \d{4}-\d{2}-\d{2} \d{2}:\d{2}$/i.test(value);
}

export interface RunChatStreamParams {
  sessionId: string;
  userMessageId: string;
  assistantMsgId: string;
  content: string;
  attachments?: File[];
  folderId?: string | null;
  /** Knowledge (or other) file UUIDs merged into attachment_paths server-side. */
  fileIds?: string[];
  /**
   * Folder bound to a code project — sent as ``project_folder_id``.
   * The backend resolves the on-disk path and folds it into
   * ``tool_extra['project_roots']`` for the coding agent and
   * ``project_*`` tools.
   */
  projectFolderId?: string | null;
  /** Resume after ``ask_user``: POST as ``tool_replies`` JSON to ``/chat/stream``. */
  toolReplies?: Array<{ tool_call_id: string; content: string }>;
  /** Model selection from the composer. Usually "provider/model"; legacy modes are still accepted. */
  modelMode?: string;
  /** When true, the backend folds the deep-research persona into the system prompt. */
  researchMode?: boolean;
  /** Active paper file name, surfaced to the deep-research persona. */
  researchDoc?: string;
  signal: AbortSignal;
  t: TFunction;
}

/**
 * POST /chat/stream and apply SSE events to the assistant message until completion or error.
 * Does not manage loading/streaming flags or AbortController lifecycle — callers own that.
 */
export async function runChatStream({
  sessionId,
  userMessageId,
  assistantMsgId,
  content,
  attachments,
  folderId,
  fileIds,
  projectFolderId,
  toolReplies,
  modelMode,
  researchMode,
  researchDoc,
  signal,
  t,
}: RunChatStreamParams): Promise<void> {
  // Reset terminal reason state from any prior turn.
  useChatStore.setState({ lastTerminalReason: null, lastCheckpointId: null });

  const formData = new FormData();
  formData.append('message', content ?? '');
  formData.append('session_id', sessionId);

  if (toolReplies?.length) {
    formData.append('tool_replies', JSON.stringify(toolReplies));
  }

  if (attachments) {
    attachments.forEach((f) => formData.append('files', f));
  }

  if (folderId) {
    formData.append('folder_id', folderId);
  }

  if (fileIds?.length) {
    formData.append('file_ids', fileIds.join(','));
  }

  if (projectFolderId) {
    formData.append('project_folder_id', projectFolderId);
  }

  if (researchMode) {
    formData.append('research_mode', 'true');
    if (researchDoc) {
      formData.append('research_doc', researchDoc);
    }
  }

  if (modelMode && modelMode !== 'auto') {
    if (modelMode === 'reasoning' || modelMode === 'max') {
      formData.append('model_mode', modelMode);
    } else {
      const slash = modelMode.indexOf('/');
      if (slash > 0) {
        formData.append('model_provider', modelMode.slice(0, slash));
        formData.append('model_name', modelMode.slice(slash + 1));
      }
    }
  }

  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    body: formData,
    signal,
    headers,
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const refreshSession = async () => {
    await useChatStore.getState().fetchSessionDetail(sessionId);
  };

  const startTitlePolling = () => {
    let attempts = 0;
    let stopped = false;
    let timer: ReturnType<typeof globalThis.setTimeout> | null = null;

    const stop = () => {
      stopped = true;
      if (timer) {
        globalThis.clearTimeout(timer);
        timer = null;
      }
    };

    const tick = () => {
      if (stopped) return;
      attempts += 1;
      void refreshSession().finally(() => {
        const title = useChatStore.getState().sessions.find((s) => s.id === sessionId)?.title;
        if (stopped || !isPlaceholderSessionTitle(title) || attempts >= TITLE_POLL_MAX_ATTEMPTS) {
          stop();
          return;
        }
        timer = globalThis.setTimeout(tick, TITLE_POLL_INTERVAL_MS);
      });
    };

    timer = globalThis.setTimeout(tick, TITLE_POLL_INTERVAL_MS);
    return stop;
  };
  // Defer title polling until first content arrives to avoid network contention
  // during the critical TTFB window.
  let stopTitlePolling: (() => void) | null = null;
  let titlePollingStarted = false;

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.replace(/\r$/, '');
        if (!trimmed.startsWith('data: ')) continue;
        const data = trimmed.slice(6).trimStart();
        if (data === '[DONE]') continue;

        try {
          const event = JSON.parse(data) as { type?: string; data?: unknown };
          applyChatStreamEvent(event, {
            sessionId,
            assistantMsgId,
            userMessageId,
            t,
          });
          if (!titlePollingStarted && event.type === 'content') {
            titlePollingStarted = true;
            stopTitlePolling = startTitlePolling();
          }
        } catch {
          // skip invalid JSON
        }
      }
    }
  } finally {
    flushPendingContentBatch();

    const msgs = useChatStore.getState().messages[sessionId] ?? [];
    const effectiveAssistantId = msgs.some((m) => m.id === assistantMsgId)
      ? assistantMsgId
      : [...msgs].reverse().find((m) => m.role === 'assistant')?.id ?? assistantMsgId;

    useChatStore.getState().updateMessage(sessionId, effectiveAssistantId, { isStreaming: false });
    useChatStore.getState().finalizeToolCalls(sessionId, effectiveAssistantId, 'success');
    useChatStore.getState().finalizeTaskProgress(sessionId, effectiveAssistantId, 'completed');

    void queryClient.invalidateQueries({ queryKey: ['agent-memory', sessionId] });
    void queryClient.invalidateQueries({ queryKey: ['prompt-preview', sessionId] });
    void refreshSession();
    // Auto-title can also run after SSE closes; leave a fresh polling window for that path.
    if (stopTitlePolling) stopTitlePolling();
    startTitlePolling();
  }
}

export function handleChatStreamFailure(
  err: unknown,
  sessionId: string,
  assistantMsgId: string,
  t: TFunction,
): void {
  const s = useChatStore.getState();
  if ((err as Error).name === 'AbortError') {
    const wasUserStop = s.lastStopWasUserInitiated;
    const existing = s.messages[sessionId]?.find((m) => m.id === assistantMsgId)?.content;
    s.updateMessage(sessionId, assistantMsgId, {
      isStreaming: false,
      content: existing || (wasUserStop
        ? t('chat.errors.stoppedByUser', { defaultValue: 'Stopped by user' })
        : t('chat.errors.cancelled')),
    });
    s.finalizeToolCalls(sessionId, assistantMsgId, 'error');
    s.finalizeTaskProgress(sessionId, assistantMsgId, wasUserStop ? 'failed' : 'failed');
    s.releaseChatStreamSession(sessionId);
  } else {
    s.setError((err as Error).message || t('chat.errors.sendShort'));
    s.updateMessage(sessionId, assistantMsgId, {
      isStreaming: false,
      content: t('chat.errors.genericRetry'),
    });
    s.finalizeToolCalls(sessionId, assistantMsgId, 'error');
    s.finalizeTaskProgress(sessionId, assistantMsgId, 'failed');
    s.releaseChatStreamSession(sessionId);
  }
}
