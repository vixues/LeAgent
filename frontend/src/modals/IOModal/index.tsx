import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { BaseModal } from '../BaseModal';
import { ChatViewWrapper, type ChatMessage } from './ChatViewWrapper';
import { SessionView, type Session } from './SessionView';
import { cn } from '@/lib/utils';

interface IOModalProps {
  isOpen: boolean;
  onClose: () => void;
  flowId: string;
  flowName: string;
  initialMessages?: ChatMessage[];
  onRunFlow?: (input: string) => Promise<string>;
}

export const IOModal = ({
  isOpen,
  onClose,
  flowId,
  flowName,
  initialMessages = [],
  onRunFlow,
}: IOModalProps) => {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [isLoading, setIsLoading] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);
  const [currentSessionId, setCurrentSessionId] = useState<string | undefined>();

  const [sessions, setSessions] = useState<Session[]>(() => [
    {
      id: 'session-1',
      name: t('modals.io.demoSession1'),
      createdAt: new Date(Date.now() - 3600000),
      lastMessageAt: new Date(Date.now() - 1800000),
      messageCount: 5,
      status: 'active',
    },
    {
      id: 'session-2',
      name: t('modals.io.demoSession2'),
      createdAt: new Date(Date.now() - 86400000),
      lastMessageAt: new Date(Date.now() - 7200000),
      messageCount: 12,
      status: 'completed',
    },
  ]);

  const handleSendMessage = useCallback(
    async (content: string) => {
      const userMessage: ChatMessage = {
        id: `msg-${Date.now()}`,
        role: 'user',
        content,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);

      try {
        let response: string;
        if (onRunFlow) {
          response = await onRunFlow(content);
        } else {
          await new Promise((resolve) => setTimeout(resolve, 1500));
          response = t('modals.io.mockReply', { content, flowName });
        }

        const assistantMessage: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          role: 'assistant',
          content: response,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMessage]);
      } catch (error) {
        const errorMessage: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          role: 'system',
          content: t('modals.io.executionError'),
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errorMessage]);
      } finally {
        setIsLoading(false);
      }
    },
    [flowName, onRunFlow, t]
  );

  const handleSelectSession = (sessionId: string) => {
    setCurrentSessionId(sessionId);
    setMessages([]);
  };

  const handleCreateSession = () => {
    const newSession: Session = {
      id: `session-${Date.now()}`,
      name: t('modals.io.newSessionNumber', { n: sessions.length + 1 }),
      createdAt: new Date(),
      lastMessageAt: new Date(),
      messageCount: 0,
      status: 'active',
    };
    setSessions((prev) => [newSession, ...prev]);
    setCurrentSessionId(newSession.id);
    setMessages([]);
  };

  const handleDeleteSession = (sessionId: string) => {
    setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    if (currentSessionId === sessionId) {
      setCurrentSessionId(undefined);
      setMessages([]);
    }
  };

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title={t('modals.io.title', { name: flowName })}
      size="full"
      className="h-[80vh]"
    >
      <div className="flex h-full -mx-6 -my-4">
        {showSidebar && (
          <div className="w-80 border-r border-border shrink-0">
            <SessionView
              sessions={sessions}
              currentSessionId={currentSessionId}
              onSelectSession={handleSelectSession}
              onCreateSession={handleCreateSession}
              onDeleteSession={handleDeleteSession}
            />
          </div>
        )}

        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex items-center justify-between px-4 py-2 border-b border-border">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setShowSidebar(!showSidebar)}
                className="p-1.5 rounded-lg text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors"
                title={showSidebar ? t('chat.hideSidebar') : t('chat.showSidebar')}
              >
                <svg
                  className={cn('w-5 h-5 transition-transform', !showSidebar && 'rotate-180')}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M11 19l-7-7 7-7m8 14l-7-7 7-7"
                  />
                </svg>
              </button>
              <div>
                <h3 className="font-medium text-foreground">
                  {currentSessionId
                    ? sessions.find((s) => s.id === currentSessionId)?.name || t('modals.io.newChat')
                    : t('modals.io.selectSession')}
                </h3>
                <p className="text-xs text-muted-foreground">
                  {flowName} • {flowId}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {isLoading && (
                <span className="text-sm text-primary-600 dark:text-primary-400 flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  {t('chat.generating')}
                </span>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-hidden">
            <ChatViewWrapper
              messages={messages}
              onSendMessage={handleSendMessage}
              isLoading={isLoading}
              placeholder={t('modals.io.inputPlaceholder')}
            />
          </div>
        </div>
      </div>
    </BaseModal>
  );
};

export { ChatViewWrapper, SessionView };
export type { ChatMessage, Session };
export default IOModal;
