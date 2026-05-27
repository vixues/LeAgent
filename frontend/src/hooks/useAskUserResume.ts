import { useCallback } from 'react';
import type { TFunction } from 'i18next';
import { isChatStreamBusyForSession, useChatStore } from '@/stores/chat';
import { runChatStream, handleChatStreamFailure } from '@/lib/runChatStream';
import { getComposerModelMode } from '@/stores/chatDraft';

/**
 * POST ``tool_replies`` to continue the same assistant message after ``ask_user``.
 */
export function useAskUserResume(t: TFunction) {
  return useCallback(
    async (answers: Record<string, string | string[]>) => {
      const store = useChatStore.getState();
      const pending = store.pendingUserInput;
      if (!pending || isChatStreamBusyForSession(pending.sessionId, store)) return;

      const snapshot = pending;
      const content = JSON.stringify({ answers });
      const toolReplies = [{ tool_call_id: pending.toolCallId, content }];

      store.updateMessage(pending.sessionId, pending.assistantMsgId, { isStreaming: true });
      store.abortActiveStreamUnlessSession(pending.sessionId);
      store.beginChatStreamSession(pending.sessionId);
      store.setError(null);

      const controller = new AbortController();
      store.setStreamAbortController(controller);
      store.clearPendingUserInput();
      try {
        await runChatStream({
          sessionId: pending.sessionId,
          userMessageId: pending.assistantMsgId,
          assistantMsgId: pending.assistantMsgId,
          content: '',
          toolReplies,
          modelMode: getComposerModelMode(),
          signal: controller.signal,
          t,
        });
        useChatStore.getState().updateToolCall(
          snapshot.sessionId,
          snapshot.assistantMsgId,
          snapshot.toolCallId,
          { status: 'success', result: { answers } },
        );
      } catch (err) {
        useChatStore.getState().setPendingUserInput(snapshot);
        handleChatStreamFailure(err, snapshot.sessionId, snapshot.assistantMsgId, t);
      } finally {
        useChatStore.getState().updateMessage(snapshot.sessionId, snapshot.assistantMsgId, {
          isStreaming: false,
        });
        useChatStore.getState().releaseChatStreamSession(snapshot.sessionId);
        useChatStore.getState().releaseStreamAbortController(controller);
      }
    },
    [t],
  );
}
