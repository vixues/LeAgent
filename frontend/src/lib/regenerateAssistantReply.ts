import type { TFunction } from 'i18next';
import { generateId, isUuid } from '@/lib/utils';
import { useChatStore } from '@/stores/chat';
import type { Message } from '@/types/chat';
import { handleChatStreamFailure, runChatStream } from '@/lib/runChatStream';

export function findPrecedingUserMessage(
  messages: Message[],
  assistantMessageId: string,
): Message | undefined {
  const idx = messages.findIndex((m) => m.id === assistantMessageId);
  if (idx <= 0) return undefined;
  for (let i = idx - 1; i >= 0; i--) {
    const m = messages[i];
    if (m?.role === 'user') return m;
  }
  return undefined;
}

/**
 * Re-runs the assistant turn for the given assistant message: drops that reply
 * and everything after it, keeps the preceding user row, and POSTs `/chat/stream`
 * again with the same user text (and UUID attachment ids when present).
 */
export async function regenerateAssistantReply(params: {
  assistantMessageId: string;
  t: TFunction;
}): Promise<void> {
  const store = useChatStore.getState();
  const sessionId = store.currentSessionId;
  if (!sessionId || store.isStreaming) return;

  const messages = store.messages[sessionId] ?? [];
  const userMsg = findPrecedingUserMessage(messages, params.assistantMessageId);
  if (!userMsg) return;

  const trimmed = userMsg.content.trim();
  const hasAttachments = Boolean(userMsg.attachments?.length);
  if (!trimmed && !hasAttachments) return;

  if (!store.truncateAfterMessageId(sessionId, userMsg.id)) return;

  const assistantMsgId = generateId();
  store.addMessage(sessionId, {
    id: assistantMsgId,
    role: 'assistant',
    content: '',
    createdAt: new Date().toISOString(),
    isStreaming: true,
    toolCalls: [],
  });

  store.setLoading(true);
  store.setStreaming(true);
  store.setError(null);

  const controller = new AbortController();
  store.setStreamAbortController(controller);

  try {
    const fileIds =
      userMsg.attachments?.map((a) => a.id).filter((id) => isUuid(id)) ?? [];
    await runChatStream({
      sessionId,
      userMessageId: userMsg.id,
      assistantMsgId,
      content: trimmed,
      fileIds: fileIds.length ? fileIds : undefined,
      signal: controller.signal,
      t: params.t,
    });
  } catch (err) {
    handleChatStreamFailure(err, sessionId, assistantMsgId, params.t);
  } finally {
    useChatStore.getState().setLoading(false);
    useChatStore.getState().setStreaming(false);
    useChatStore.getState().releaseStreamAbortController(controller);
  }
}
