import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { BookOpen, LayoutTemplate, PawPrint, ArrowDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useDailyChatGreetings } from '@/hooks/useDailyChatGreetings';
import { PetSceneStage } from '@/components/pet/PetSceneStage';
import { useChatStore } from '@/stores/chat';
import { findPrecedingUserMessage } from '@/lib/regenerateAssistantReply';
import { AgentMessage } from './AgentMessage';
import { UserMessage } from './UserMessage';
import type { Message } from '@/types/chat';

interface ChatMessagesProps {
  className?: string;
  onSuggestionClick?: (content: string) => void;
  onEditAndResend?: (userMessageId: string, newContent: string) => void | Promise<void>;
}

const emptyCardFocus = cn(
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/30',
  'focus-visible:ring-offset-2 focus-visible:ring-offset-background',
);

function EmptyStateMascot() {
  return (
    <div className="relative z-10 mx-auto mb-6 h-24 w-24 min-h-0 min-w-0 overflow-visible">
      <PetSceneStage surface="chatEmpty" className="h-full w-full" />
    </div>
  );
}

/** Hero greeting: long dwell between lines, slow crossfade (pairs with `.chat-empty-greeting`). */
const EMPTY_GREETING_ROTATE_MS = 60_000;
const EMPTY_GREETING_CROSSFADE_MS = 1000;

function RotatingEmptyGreeting({ lines }: { lines: string[] }) {
  const [idx, setIdx] = useState(0);
  const [visible, setVisible] = useState(true);
  const pool = lines.length ? lines : [''];
  const canRotate = pool.length > 1;
  const lineKey = pool.join('\u0001');
  const poolRef = useRef(pool);
  poolRef.current = pool;

  useEffect(() => {
    setIdx(0);
    setVisible(true);
  }, [lineKey]);

  useEffect(() => {
    if (!canRotate) return;
    const tick = window.setInterval(() => {
      setVisible(false);
      window.setTimeout(() => {
        const len = poolRef.current.length;
        if (len < 2) return;
        setIdx((i) => (i + 1) % len);
        setVisible(true);
      }, EMPTY_GREETING_CROSSFADE_MS);
    }, EMPTY_GREETING_ROTATE_MS);
    return () => window.clearInterval(tick);
  }, [canRotate, lineKey]);

  return (
    <div className="chat-empty-greeting-wrap mb-8 flex min-h-[2.75rem] items-center justify-center">
      <h2
        className={cn(
          'chat-empty-greeting text-3xl font-semibold tracking-tight text-foreground',
          visible ? 'chat-empty-greeting--show' : 'chat-empty-greeting--hide',
        )}
        aria-live="polite"
      >
        {pool[idx] ?? ''}
      </h2>
    </div>
  );
}

export function ChatMessages({
  className,
  onSuggestionClick,
  onEditAndResend,
}: ChatMessagesProps) {
  const { t } = useTranslation();
  const dailyGreetings = useDailyChatGreetings();
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const isStreaming = useChatStore((state) => state.isStreaming);
  const messagesMap = useChatStore((state) => state.messages);
  const messagePages = useChatStore((state) => state.messagePages);
  const messagesLoadingSessionId = useChatStore((state) => state.messagesLoadingSessionId);
  const fetchOlderMessages = useChatStore((state) => state.fetchOlderMessages);
  const messages: Message[] = currentSessionId
    ? (messagesMap[currentSessionId] ?? [])
    : [];
  const streamTailForScroll = useMemo(() => {
    const m = messages.at(-1);
    if (!m) return '';
    const tcChars =
      m.toolCalls?.reduce((acc, tc) => acc + (tc.argumentsRaw?.length ?? 0), 0) ?? 0;
    return `${m.id}:${m.content.length}:${tcChars}:${m.isStreaming}`;
  }, [messages]);
  const pageState = currentSessionId ? messagePages[currentSessionId] : undefined;
  const hasOlderMessages = Boolean(pageState?.hasOlder);
  const isLoadingOlderMessages = Boolean(pageState?.isLoadingOlder);
  const threadLoading =
    Boolean(currentSessionId) &&
    messages.length === 0 &&
    messagesLoadingSessionId === currentSessionId;
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const prevSessionIdRef = useRef<string | null>(null);
  const prevMessageCountRef = useRef(0);
  const prependScrollHeightRef = useRef<number | null>(null);
  const [isNearBottom, setIsNearBottom] = useState(true);
  const [showJumpPill, setShowJumpPill] = useState(false);

  const loadOlderMessages = useCallback(() => {
    if (!currentSessionId || !hasOlderMessages || isLoadingOlderMessages) return;
    const el = scrollContainerRef.current;
    prependScrollHeightRef.current = el?.scrollHeight ?? null;
    void fetchOlderMessages(currentSessionId);
  }, [currentSessionId, fetchOlderMessages, hasOlderMessages, isLoadingOlderMessages]);

  // Track whether user is near the bottom via IntersectionObserver
  useEffect(() => {
    const sentinel = sentinelRef.current;
    const container = scrollContainerRef.current;
    if (!sentinel || !container) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry) return;
        const near = entry.isIntersecting;
        setIsNearBottom(near);
        setShowJumpPill(!near && messages.length > 0);
      },
      { root: container, rootMargin: '120px 0px 0px 0px', threshold: 0 },
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [messages.length]);

  /**
   * Re-opening or switching sessions reused the same scroll node; keeping the old
   * scrollTop with shorter content pushed the thread out of view (broken layout).
   * Snap to bottom when the session changes or when the first page of messages arrives.
   */
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!currentSessionId) {
      prevSessionIdRef.current = null;
      prevMessageCountRef.current = 0;
      return;
    }

    const sessionChanged = prevSessionIdRef.current !== currentSessionId;
    if (sessionChanged) {
      prevSessionIdRef.current = currentSessionId;
    }

    const len = messages.length;
    const prevLen = prevMessageCountRef.current;
    prevMessageCountRef.current = len;

    if (!el) return;
    if (len === 0) {
      el.scrollTop = 0;
      return;
    }

    const initialHydrate = !sessionChanged && prevLen === 0 && len > 0;
    if (sessionChanged || initialHydrate) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          const node = scrollContainerRef.current;
          if (node) node.scrollTop = node.scrollHeight;
        });
      });
    } else if (prependScrollHeightRef.current != null) {
      const prevHeight = prependScrollHeightRef.current;
      prependScrollHeightRef.current = null;
      requestAnimationFrame(() => {
        const node = scrollContainerRef.current;
        if (node) node.scrollTop += node.scrollHeight - prevHeight;
      });
    }
  }, [currentSessionId, messages.length]);

  /**
   * Streaming auto-scroll. During streaming every token append re-renders the
   * list; smooth `scrollIntoView` is expensive and fights with user scroll.
   * We use a rAF-throttled direct scrollTop write so there's at most one
   * update per frame.
   */
  const scrollRafRef = useRef<number | null>(null);
  const scheduleScrollToBottom = useCallback(() => {
    if (scrollRafRef.current != null) return;
    scrollRafRef.current = requestAnimationFrame(() => {
      scrollRafRef.current = null;
      const el = scrollContainerRef.current;
      if (!el) return;
      el.scrollTop = el.scrollHeight;
    });
  }, []);

  useEffect(() => {
    if (isStreaming && isNearBottom) scheduleScrollToBottom();
  }, [streamTailForScroll, isStreaming, isNearBottom, scheduleScrollToBottom]);

  useEffect(() => {
    return () => {
      if (scrollRafRef.current != null) {
        cancelAnimationFrame(scrollRafRef.current);
      }
    };
  }, []);

  const jumpToLatest = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, []);

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el || el.scrollTop > 96) return;
    loadOlderMessages();
  }, [loadOlderMessages]);

  // Thread skeleton: same chrome as the message list so reopen/switch does not flash the "new chat" layout.
  if (threadLoading) {
    return (
      <div
        ref={scrollContainerRef}
        className={cn('chat-messages-scroll min-h-0', className)}
        role="status"
        aria-busy="true"
        aria-label={t('chat.loadingThread', { defaultValue: 'Loading messages' })}
      >
        <div className="mx-auto w-full max-w-[72ch] pl-20 pr-6 py-6 space-y-8">
          <div className="space-y-3 animate-pulse">
            <div className="h-3 w-24 rounded bg-muted" />
            <div className="h-20 rounded-xl bg-muted/70" />
          </div>
          <div className="space-y-3 animate-pulse">
            <div className="h-3 w-32 rounded bg-muted" />
            <div className="h-32 rounded-xl bg-muted/70" />
            <div className="h-24 rounded-xl bg-muted/50" />
          </div>
        </div>
      </div>
    );
  }

  // Empty state
  if (messages.length === 0) {
    return (
      <div
        ref={scrollContainerRef}
        className={cn(
          'chat-messages-scroll flex flex-col items-center justify-center min-h-0 h-full pl-20 pr-6',
          className,
        )}
      >
        <div
          className={cn(
            'mx-auto w-full max-w-5xl px-1 text-center sm:px-0',
            'translate-y-[clamp(0.75rem,3.5vh,2.75rem)] motion-reduce:translate-y-0',
          )}
        >
          <EmptyStateMascot />

          <RotatingEmptyGreeting lines={dailyGreetings} />

          <div className="mx-auto flex w-full flex-row flex-wrap justify-center gap-3 text-left">
            <button
              type="button"
              onClick={() => onSuggestionClick?.(t('chat.suggestions.intro.prompt'))}
              className={cn(
                'chat-empty-card chat-empty-card--intro group cursor-pointer',
                emptyCardFocus,
              )}
            >
              <span className="chat-empty-card__aurora" aria-hidden />
              <span className="chat-empty-card__shine" aria-hidden />
              <span className="chat-empty-card__body">
                <span className="chat-empty-card__iconZone">
                  <BookOpen className="chat-empty-card__icon" />
                </span>
                <span className="chat-empty-card__textZone">
                  <span className="chat-empty-card__text">{t('chat.suggestions.intro.label')}</span>
                </span>
              </span>
            </button>
            <button
              type="button"
              onClick={() => onSuggestionClick?.(t('chat.suggestions.genuiResume.prompt'))}
              className={cn(
                'chat-empty-card chat-empty-card--genui group cursor-pointer',
                emptyCardFocus,
              )}
            >
              <span className="chat-empty-card__aurora" aria-hidden />
              <span className="chat-empty-card__shine" aria-hidden />
              <span className="chat-empty-card__body">
                <span className="chat-empty-card__iconZone">
                  <LayoutTemplate className="chat-empty-card__icon" />
                </span>
                <span className="chat-empty-card__textZone">
                  <span className="chat-empty-card__text">{t('chat.suggestions.genuiResume.label')}</span>
                </span>
              </span>
            </button>
            <Link
              to="/pet-space"
              className={cn(
                'chat-empty-card chat-empty-card--pet group cursor-pointer no-underline',
                emptyCardFocus,
              )}
            >
              <span className="chat-empty-card__aurora" aria-hidden />
              <span className="chat-empty-card__shine" aria-hidden />
              <span className="chat-empty-card__body">
                <span className="chat-empty-card__iconZone">
                  <PawPrint className="chat-empty-card__icon" />
                </span>
                <span className="chat-empty-card__textZone">
                  <span className="chat-empty-card__text">{t('chat.suggestions.petSpace.label')}</span>
                  <span className="chat-empty-card__hint">{t('chat.suggestions.petSpace.hint')}</span>
                </span>
              </span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={scrollContainerRef}
      onScroll={handleScroll}
      className={cn('chat-messages-scroll min-h-0', className)}
    >
      <div className="mx-auto w-full max-w-[72ch] pl-20 pr-6 py-6 space-y-8">
        {hasOlderMessages || isLoadingOlderMessages ? (
          <div className="flex justify-center">
            <button
              type="button"
              onClick={loadOlderMessages}
              disabled={isLoadingOlderMessages}
              className={cn(
                'rounded-full border border-border-subtle bg-surface px-3 py-1.5',
                'text-xs font-medium text-muted-foreground shadow-soft',
                'hover:text-foreground hover:bg-surface-sunken disabled:opacity-60',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/30',
              )}
            >
              {isLoadingOlderMessages
                ? t('chat.loadingOlderMessages', { defaultValue: 'Loading older messages...' })
                : t('chat.loadOlderMessages', { defaultValue: 'Load older messages' })}
            </button>
          </div>
        ) : null}
        {messages.map((message) =>
          message.role === 'user' ? (
            <UserMessage
              key={message.id}
              message={message}
              isStreaming={isStreaming}
              onEditAndResend={onEditAndResend}
              sessionId={currentSessionId}
            />
          ) : (
            <AgentMessage
              key={message.id}
              message={message}
              sessionId={currentSessionId}
              streamActive={isStreaming}
              precedingUserForRegenerate={findPrecedingUserMessage(messages, message.id)}
            />
          ),
        )}
        <div ref={sentinelRef} className="h-1" aria-hidden="true" />
      </div>

      {/* Jump to latest pill */}
      {showJumpPill && (
        <div className="sticky bottom-4 flex justify-center pointer-events-none">
          <button
            type="button"
            onClick={jumpToLatest}
            className={cn(
              'chat-jump-pill pointer-events-auto',
              'inline-flex items-center gap-1.5 px-3 py-1.5',
              'bg-surface border border-border-subtle rounded-full shadow-soft',
              'text-xs font-medium text-muted-foreground hover:text-foreground',
              'transition-colors duration-150',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/30',
            )}
            aria-label={t('chat.jumpToLatest', {
              defaultValue: 'Jump to latest',
            })}
          >
            <ArrowDown className="w-3 h-3" />
            {t('chat.jumpToLatest', { defaultValue: 'Jump to latest' })}
          </button>
        </div>
      )}
    </div>
  );
}
