import { useCallback } from 'react';
import type { TFunction } from 'i18next';
import { apiClient } from '@/api/client';
import { isChatStreamBusyForSession, useChatStore } from '@/stores/chat';
import { runChatStream, handleChatStreamFailure } from '@/lib/runChatStream';
import { getComposerModelMode } from '@/stores/chatDraft';
import { generateId } from '@/lib/utils';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

/**
 * Resume from a durable checkpoint after a turn that stopped with
 * `max_turns`, `token_budget_exceeded`, or any other non-completed
 * terminal reason where a `checkpoint_id` was stamped on the result.
 *
 * The flow:
 * 1. Validate the checkpoint exists (POST /resume-checkpoint).
 * 2. Stream a new turn (POST /stream with checkpoint context).
 */
export function useCheckpointResume(t: TFunction) {
  return useCallback(
    async (sessionId: string, prompt = '') => {
      const store = useChatStore.getState();
      const checkpointId = store.lastCheckpointId;
      if (!checkpointId || isChatStreamBusyForSession(sessionId, store)) return;

      try {
        await apiClient.post(`${API_BASE}/chat/sessions/${sessionId}/resume-checkpoint`, {
          checkpoint_id: checkpointId,
          prompt,
        });
      } catch {
        store.setError(t('chat.errors.genericRetry'));
        return;
      }

      const assistantMsgId = generateId();
      store.addMessage(sessionId, {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        isStreaming: true,
      } as import('@/types/chat').Message);

      store.abortActiveStreamUnlessSession(sessionId);
      store.beginChatStreamSession(sessionId);
      store.setError(null);

      const controller = new AbortController();
      store.setStreamAbortController(controller);

      try {
        await runChatStream({
          sessionId,
          userMessageId: assistantMsgId,
          assistantMsgId,
          content: prompt || 'Continue',
          modelMode: getComposerModelMode(),
          signal: controller.signal,
          t,
        });
      } catch (err) {
        handleChatStreamFailure(err, sessionId, assistantMsgId, t);
      } finally {
        useChatStore.getState().releaseChatStreamSessionAndResync(sessionId);
        useChatStore.getState().releaseStreamAbortController(controller);
      }
    },
    [t],
  );
}
