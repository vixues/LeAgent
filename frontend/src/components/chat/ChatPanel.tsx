import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { isChatStreamBusyForSession, useChatStore } from '@/stores/chat';
import { buildComposerSendParams, getComposerModelMode, resetComposerAfterSend } from '@/stores/chatDraft';
import { generateId } from '@/lib/utils';
import { GenUiActionBridge } from '@/components/canvas/genUi/GenUiActionBridge';
import { ChatHeader } from './ChatHeader';
import { ChatMessages } from './ChatMessages';
import { ChatInput } from './ChatInput';
import { ChatComposerUserInputGate } from '@/components/chat/ChatComposerUserInputGate';
import type { Message, SendMessageParams } from '@/types/chat';
import { handleChatStreamFailure, runChatStream } from '@/lib/runChatStream';
import { useAskUserResume } from '@/hooks/useAskUserResume';

interface ChatPanelProps {
  className?: string;
}

export function ChatPanel({ className }: ChatPanelProps) {
  const { t } = useTranslation();
  const onAskUserResume = useAskUserResume(t);

  const createSession = useChatStore((state) => state.createSession);
  const clearMessages = useChatStore((state) => state.clearMessages);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const setError = useChatStore((state) => state.setError);

  const handleNewSession = useCallback(() => {
    createSession();
  }, [createSession]);

  const handleClearMessages = useCallback(() => {
    if (!currentSessionId) return;
    if (window.confirm(t('chat.confirmClear'))) {
      clearMessages(currentSessionId);
    }
  }, [currentSessionId, clearMessages, t]);

  const sendMessage = useCallback(
    async ({ content, attachments, folderId, fileIds, projectFolderId, modelMode }: SendMessageParams) => {
      const store = useChatStore.getState();
      let sessionId: string = store.currentSessionId ?? await store.createSession();

      const userMessageId = generateId();
      const userMessage: Message = {
        id: userMessageId,
        role: 'user',
        content,
        createdAt: new Date().toISOString(),
        attachments: attachments?.map((f) => ({
          id: generateId(),
          name: f.name,
          type: f.type,
          size: f.size,
        })),
      };

      store.addMessage(sessionId, userMessage);

      const assistantMsgId = generateId();
      const assistantMessage: Message = {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        createdAt: new Date().toISOString(),
        isStreaming: true,
        toolCalls: [],
      };

      store.addMessage(sessionId, assistantMessage);
      store.abortActiveStreamUnlessSession(sessionId);
      store.beginChatStreamSession(sessionId);
      store.setError(null);

      resetComposerAfterSend();

      const controller = new AbortController();
      useChatStore.getState().setStreamAbortController(controller);

      try {
        await runChatStream({
          sessionId,
          userMessageId,
          assistantMsgId,
          content,
          attachments,
          folderId,
          fileIds,
          projectFolderId,
          modelMode,
          signal: controller.signal,
          t,
        });
      } catch (err) {
        handleChatStreamFailure(err, sessionId, assistantMsgId, t);
      } finally {
        useChatStore.getState().releaseChatStreamSession(sessionId);
        useChatStore.getState().releaseStreamAbortController(controller);
      }
    },
    [t]
  );

  const handleEditResend = useCallback(
    async (userMessageId: string, newContent: string) => {
      const trimmed = newContent.trim();
      if (!trimmed) return;

      const store = useChatStore.getState();
      const sessionId = store.currentSessionId;
      if (!sessionId || isChatStreamBusyForSession(sessionId, store)) return;

      if (!store.truncateAfterMessageId(sessionId, userMessageId)) return;

      store.updateMessage(sessionId, userMessageId, { content: trimmed });
      useChatStore.setState((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === sessionId
            ? {
                ...sess,
                preview: trimmed.slice(0, 50),
                updatedAt: new Date().toISOString(),
              }
            : sess
        ),
      }));

      const assistantMsgId = generateId();
      store.addMessage(sessionId, {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        createdAt: new Date().toISOString(),
        isStreaming: true,
        toolCalls: [],
      });

      store.abortActiveStreamUnlessSession(sessionId);
      store.beginChatStreamSession(sessionId);
      store.setError(null);

      const controller = new AbortController();
      useChatStore.getState().setStreamAbortController(controller);

      try {
        await runChatStream({
          sessionId,
          userMessageId,
          assistantMsgId,
          content: trimmed,
          modelMode: getComposerModelMode(),
          signal: controller.signal,
          t,
        });
      } catch (err) {
        handleChatStreamFailure(err, sessionId, assistantMsgId, t);
      } finally {
        useChatStore.getState().releaseChatStreamSession(sessionId);
        useChatStore.getState().releaseStreamAbortController(controller);
      }
    },
    [t],
  );

  const stopStreaming = useCallback(() => {
    useChatStore.getState().abortChatStreamFromUser();
  }, []);

  const handleSend = useCallback(
    async (
      content: string,
      files?: File[],
      folderId?: string | null,
      fileIds?: string[],
      projectFolderId?: string | null,
      modelMode?: string,
    ) => {
      await sendMessage({ content, attachments: files, folderId, fileIds, projectFolderId, modelMode });
    },
    [sendMessage],
  );

  const handleSendWithSuggestion = useCallback(
    async (suggestionPrompt: string) => {
      const store = useChatStore.getState();
      if (isChatStreamBusyForSession(store.currentSessionId, store)) return;
      const { content, attachments, folderId, fileIds, projectFolderId, modelMode } =
        buildComposerSendParams(suggestionPrompt);
      if (!content.trim() && !attachments?.length) return;
      await handleSend(content, attachments, folderId, fileIds, projectFolderId, modelMode);
    },
    [handleSend],
  );

  const error = useChatStore((state) => state.error);

  return (
    <div
      className={cn(
        'relative flex flex-col h-full',
        'bg-surface',
        className
      )}
    >
      <GenUiActionBridge />
      <ChatHeader
        onNewSession={handleNewSession}
        onClearMessages={handleClearMessages}
      />

      {error && (
        <div className="px-4 py-2 bg-red-50 dark:bg-red-900/20 border-b border-red-200 dark:border-red-800 flex-shrink-0 flex items-center justify-between gap-2">
          <p className="text-xs text-red-600 dark:text-red-400 flex-1">{error}</p>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-xs text-red-500 hover:text-red-700 dark:hover:text-red-300 font-medium"
          >
            {t('chat.closePanel')}
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        <ChatMessages
          onSuggestionClick={handleSendWithSuggestion}
          onEditAndResend={handleEditResend}
        />
      </div>

      <ChatComposerUserInputGate onSubmitAnswers={onAskUserResume} />
      <ChatInput onSend={handleSend} onStop={stopStreaming} />
    </div>
  );
}
