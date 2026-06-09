import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Panel, Group, Separator } from 'react-resizable-panels';
import { isChatStreamBusyForSession, useChatStore } from '@/stores/chat';
import { buildComposerSendParams, getComposerModelMode, resetComposerAfterSend } from '@/stores/chatDraft';
import { useArtifactStore } from '@/stores/artifact';
import { useLayoutStore } from '@/stores/layout';
import { generateId } from '@/lib/utils';
import { ChatMessages } from '@/components/chat/ChatMessages';
import { ChatPinnedStrip } from '@/components/chat/ChatPinnedStrip';
import { ChatInput } from '@/components/chat/ChatInput';
import { ChatComposerUserInputGate } from '@/components/chat/ChatComposerUserInputGate';
import { ChatTerminalReasonBanner } from '@/components/chat/ChatTerminalReasonBanner';
import { ChatFabBar } from '@/components/chat/ChatFabBar';
import { ChatErrorToast } from '@/components/chat/ChatErrorToast';
import { ChatCommandPalette } from '@/components/chat/ChatCommandPalette';
import { RightPanel } from '@/components/chat/RightPanel';
import type { Message, SendMessageParams } from '@/types/chat';
import { handleChatStreamFailure, runChatStream } from '@/lib/runChatStream';
import { useAskUserResume } from '@/hooks/useAskUserResume';
import { useMediaQuery } from '@/hooks/useMobile';
import { extractApiFileDownloadId } from '@/components/chat/media/chatMediaUtils';
import { downloadAuthenticatedFile } from '@/lib/downloadAuthenticatedFile';

/** Matches Tailwind `lg` — keep chat column mounted once (see ChatView layout). */
const LG_MIN = '(min-width: 1024px)';

const DOWNLOAD_COMMAND_RE = /^(download|下载)\s+["“]?(.+?)["”]?$/i;

type DownloadCandidate = {
  name: string;
  url: string;
};
type DownloadResolution =
  | { kind: 'found'; candidate: DownloadCandidate }
  | { kind: 'ambiguous'; options: string[] }
  | { kind: 'none' };

export default function ChatView() {
  const { t } = useTranslation();
  const onAskUserResume = useAskUserResume(t);

  const openTabIds = useArtifactStore((s) => s.openTabIds);
  const workspaceOpen = useLayoutStore((s) => s.workspaceOpen);
  const setWorkspaceOpen = useLayoutStore((s) => s.setWorkspaceOpen);
  const focusMode = useLayoutStore((s) => s.focusMode);
  const toggleFocusMode = useLayoutStore((s) => s.toggleFocusMode);
  const setChatHistoryOpen = useLayoutStore((s) => s.setChatHistoryOpen);

  const showRightPanel = openTabIds.length > 0 || workspaceOpen;
  const isLg = useMediaQuery(LG_MIN);

  const createSession = useChatStore((state) => state.createSession);
  const clearMessages = useChatStore((state) => state.clearMessages);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const stopCodingProjectsForSession = useChatStore((s) => s.stopCodingProjectsForSession);
  const setError = useChatStore((state) => state.setError);
  const error = useChatStore((state) => state.error);
  const prevSessionIdRef = useRef<string | null>(null);

  useEffect(() => {
    const prev = prevSessionIdRef.current;
    prevSessionIdRef.current = currentSessionId;
    if (prev !== null && prev !== currentSessionId) {
      void stopCodingProjectsForSession(prev);
    }
  }, [currentSessionId, stopCodingProjectsForSession]);

  useEffect(() => {
    return () => {
      const sid = useChatStore.getState().currentSessionId;
      void useChatStore.getState().stopCodingProjectsForSession(sid);
    };
  }, [stopCodingProjectsForSession]);

  // Persist restores `currentSessionId` but not `messages`; sync after storage rehydrates (may be async).
  // Also triggers fetchSessions to reconcile stale persisted state with the server.
  useEffect(() => {
    const pull = async () => {
      const store = useChatStore.getState();
      await store.fetchSessions();
      const id = useChatStore.getState().currentSessionId;
      if (id) void useChatStore.getState().fetchMessages(id);
    };
    if (useChatStore.persist.hasHydrated()) {
      void pull();
      return;
    }
    return useChatStore.persist.onFinishHydration(() => {
      void pull();
    });
  }, []);

  const triggerBrowserDownload = useCallback((name: string, url: string) => {
    const fileId = extractApiFileDownloadId(url);
    if (fileId) {
      void downloadAuthenticatedFile(fileId, name);
      return;
    }
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = name;
    anchor.target = '_blank';
    anchor.rel = 'noopener noreferrer';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  }, []);

  const resolveDownloadCandidate = useCallback(
    (sessionId: string, wantedName: string): DownloadResolution => {
      const target = wantedName.trim().toLowerCase();
      const messages = useChatStore.getState().messages[sessionId] ?? [];

      const candidates: DownloadCandidate[] = [];
      for (const msg of messages) {
        for (const att of msg.attachments ?? []) {
          if (!att.name) continue;
          const url = att.downloadUrl ?? att.url ?? `/api/v1/files/${att.id}/download`;
          candidates.push({ name: att.name, url });
        }
      }

      const artifacts = Object.values(useArtifactStore.getState().artifacts);
      for (const artifact of artifacts) {
        const fileId = artifact.metadata?.fileId;
        if (typeof fileId === 'string') {
          candidates.push({
            name: artifact.title,
            url: `/api/v1/files/${fileId}/download`,
          });
        }
      }

      const exact = candidates.find((c) => c.name.toLowerCase() === target);
      if (exact) return { kind: 'found', candidate: exact };

      const fuzzy = candidates.filter((c) => c.name.toLowerCase().includes(target));
      if (fuzzy.length === 1) {
        const candidate = fuzzy[0];
        if (candidate) {
          return { kind: 'found', candidate };
        }
      }
      if (fuzzy.length > 1) {
        return { kind: 'ambiguous', options: fuzzy.slice(0, 5).map((f) => f.name) };
      }
      return { kind: 'none' };
    },
    [],
  );

  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setCommandPaletteOpen((prev) => !prev);
      }
      if ((e.metaKey || e.ctrlKey) && e.key === '\\') {
        e.preventDefault();
        toggleFocusMode();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [toggleFocusMode]);

  // When focus mode turns on, collapse both rails for maximum immersion.
  useEffect(() => {
    if (focusMode) {
      setChatHistoryOpen(false);
      setWorkspaceOpen(false);
    }
  }, [focusMode, setChatHistoryOpen, setWorkspaceOpen]);

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
      const sessionId: string =
        store.currentSessionId ?? (await store.createSession());

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
    [t],
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
      const trimmed = content.trim();
      const commandMatch = trimmed.match(DOWNLOAD_COMMAND_RE);
      if (commandMatch) {
        const requestedName = commandMatch[2] ?? '';
        const store = useChatStore.getState();
        const sessionId: string =
          store.currentSessionId ?? (await store.createSession());
        const resolved = resolveDownloadCandidate(sessionId, requestedName);

        if (resolved.kind === 'found') {
          triggerBrowserDownload(resolved.candidate.name, resolved.candidate.url);
          store.addMessage(sessionId, {
            id: generateId(),
            role: 'system',
            content: `Download started: ${resolved.candidate.name}`,
            createdAt: new Date().toISOString(),
          });
          return;
        }
        if (resolved.kind === 'ambiguous') {
          store.addMessage(sessionId, {
            id: generateId(),
            role: 'system',
            content: `Multiple files matched "${requestedName}". Please be specific: ${resolved.options.join(', ')}`,
            createdAt: new Date().toISOString(),
          });
          return;
        }
        store.addMessage(sessionId, {
          id: generateId(),
          role: 'system',
          content: `No matching downloadable file found for "${requestedName}".`,
          createdAt: new Date().toISOString(),
        });
        return;
      }
      await sendMessage({ content, attachments: files, folderId, fileIds, projectFolderId, modelMode });
    },
    [resolveDownloadCandidate, sendMessage, triggerBrowserDownload],
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

  const handleRightPanelResize = useCallback(
    (panelSize: { asPercentage: number; inPixels: number }) => {
      if (panelSize.inPixels <= 0 || panelSize.asPercentage <= 0) {
        setWorkspaceOpen(false);
        useArtifactStore.setState({ openTabIds: [], activeTabId: null });
      }
    },
    [setWorkspaceOpen],
  );

  const desktopCenterGrid = (
    <div className="chat-center-grid">
      <ChatFabBar
        onNewSession={handleNewSession}
        onClearMessages={handleClearMessages}
        onOpenCommandPalette={() => setCommandPaletteOpen(true)}
        onToggleFocus={toggleFocusMode}
        focusMode={focusMode}
      />
      <div className="chat-center-main">
        <ChatPinnedStrip />
        <ChatMessages
          className="flex-1 min-h-0"
          onSuggestionClick={handleSendWithSuggestion}
          onEditAndResend={handleEditResend}
        />
      </div>
      <div className="chat-composer-row">
        <div className="chat-composer-inner">
          {error && (
            <div className="absolute bottom-full left-0 right-0 mb-2 pointer-events-none">
              <ChatErrorToast
                message={error}
                onDismiss={() => setError(null)}
                className="pointer-events-auto"
              />
            </div>
          )}
          <ChatTerminalReasonBanner />
          <ChatComposerUserInputGate onSubmitAnswers={onAskUserResume} />
          <ChatInput onSend={handleSend} onStop={stopStreaming} />
        </div>
      </div>
    </div>
  );

  /**
   * One chat column mount only: previously we rendered the same `desktopCenterGrid` under
   * `hidden lg:flex` and again under `flex lg:hidden`. Both stayed in the React tree; broken
   * `display`/breakpoint layering could show both — the conversation appeared 2–3×.
   * Branch on `isLg` so FabBar + ChatMessages + composer exist in a single subtree.
   */
  const chatLayoutMain =
    showRightPanel && isLg ? (
      <Group
        orientation="horizontal"
        id="chat-layout"
        className="flex flex-1 min-h-0 min-w-0"
      >
        <Panel id="chat-center" defaultSize={60} minSize="35%">
          {desktopCenterGrid}
        </Panel>
        <Separator />
        <Panel
          id="chat-right"
          defaultSize="40%"
          minSize="20%"
          maxSize="55%"
          collapsible
          onResize={handleRightPanelResize}
          className="flex min-h-0 min-w-0 flex-col !overflow-hidden px-2 pb-2 pt-[10px]"
        >
          <RightPanel />
        </Panel>
      </Group>
    ) : (
      <div id="chat-layout" className="flex flex-1 min-h-0 min-w-0 flex-col">
        {desktopCenterGrid}
      </div>
    );

  return (
    <div
      className="chat-surface relative flex min-h-0 min-w-0 flex-1 overflow-hidden"
      data-focus={focusMode ? 'true' : 'false'}
    >
      {chatLayoutMain}

      {/* Workspace drawer: small viewports only (wide layout uses inline RightPanel above). */}
      {showRightPanel && !isLg ? (
        <>
          <div
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40 animate-fade-in"
            onClick={() => {
              setWorkspaceOpen(false);
              useArtifactStore.getState().closeArtifact();
              useArtifactStore.setState({ openTabIds: [], activeTabId: null });
            }}
            aria-hidden="true"
          />
          <div className="fixed left-auto top-[10px] bottom-2 right-2 z-50 flex h-auto min-h-0 w-[min(92vw,28rem)] max-w-md flex-col animate-fade-in">
            <RightPanel />
          </div>
        </>
      ) : null}

      <ChatCommandPalette
        open={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
      />
    </div>
  );
}
