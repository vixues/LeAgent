import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
}

interface ChatViewWrapperProps {
  messages: ChatMessage[];
  onSendMessage: (content: string) => void;
  isLoading?: boolean;
  placeholder?: string;
}

export const ChatViewWrapper = ({
  messages,
  onSendMessage,
  isLoading = false,
  placeholder,
}: ChatViewWrapperProps) => {
  const { t } = useTranslation();
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = () => {
    if (!input.trim() || isLoading) return;
    onSendMessage(input.trim());
    setInput('');
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <div className="text-center">
              <svg
                className="w-12 h-12 mx-auto mb-4 text-muted-foreground-tertiary"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                />
              </svg>
              <p>{t('modals.io.noMessages')}</p>
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={cn(
                'flex',
                message.role === 'user' ? 'justify-end' : 'justify-start'
              )}
            >
              <div
                className={cn(
                  'max-w-[80%] rounded-lg px-4 py-2',
                  message.role === 'user'
                    ? 'bg-primary-600 text-white'
                    : 'bg-surface-sunken text-foreground',
                  message.role === 'system' && 'bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-200 text-sm'
                )}
              >
                <div className="whitespace-pre-wrap break-words">
                  {message.content}
                  {message.isStreaming && (
                    <span className="inline-block w-2 h-4 ml-1 bg-current animate-pulse" />
                  )}
                </div>
                <div
                  className={cn(
                    'text-xs mt-1 opacity-70',
                    message.role === 'user' ? 'text-right' : 'text-left'
                  )}
                >
                  {new Date(message.timestamp).toLocaleTimeString()}
                </div>
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-border p-4">
        <div className="flex gap-3">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder || t('modals.io.inputPlaceholder')}
            disabled={isLoading}
            rows={1}
            className={cn(
              'flex-1 resize-none rounded-lg border px-4 py-2 text-sm',
              'bg-surface text-foreground',
              'border-border',
              'focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'max-h-32'
            )}
            style={{ minHeight: '40px' }}
          />
          <Button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            loading={isLoading}
          >
            {t('chat.send')}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          {t('chat.inputHint')}
        </p>
      </div>
    </div>
  );
};

export default ChatViewWrapper;
