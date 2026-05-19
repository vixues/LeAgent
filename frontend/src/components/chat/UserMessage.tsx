import { useState, useCallback, useRef, useEffect, useMemo, memo } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Check, Pencil, FileText, Puzzle, Pin } from 'lucide-react';
import { cn, formatDate } from '@/lib/utils';
import { Button } from '@/components/ui/Button';
import { parseUserMessageRefs } from '@/lib/parseUserMessageRefs';
import { useChatStore } from '@/stores/chat';
import { AttachmentCard } from './AttachmentCard';
import type { Message } from '@/types/chat';

interface UserMessageProps {
  message: Message;
  className?: string;
  isStreaming?: boolean;
  onEditAndResend?: (userMessageId: string, newContent: string) => void | Promise<void>;
  sessionId?: string | null;
}

function UserMessageInner({
  message,
  className,
  isStreaming = false,
  onEditAndResend,
  sessionId = null,
}: UserMessageProps) {
  const { t } = useTranslation();
  const togglePinMessage = useChatStore((s) => s.togglePinMessage);
  const isPinned = useChatStore((s) => {
    if (!sessionId) return false;
    const sess = s.sessions.find((x) => x.id === sessionId);
    return sess?.pinnedMessageIds?.includes(message.id) ?? false;
  });
  const [copied, setCopied] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(message.content);
  const [submitting, setSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!isEditing) setDraft(message.content);
  }, [message.content, isEditing]);

  useEffect(() => {
    if (!isEditing) return;
    const el = textareaRef.current;
    if (!el) return;
    el.focus();
    const len = el.value.length;
    el.setSelectionRange(len, len);
  }, [isEditing]);

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [message.content]);

  const startEdit = useCallback(() => {
    if (!onEditAndResend || isStreaming) return;
    setDraft(message.content);
    setIsEditing(true);
  }, [onEditAndResend, isStreaming, message.content]);

  const cancelEdit = useCallback(() => {
    setDraft(message.content);
    setIsEditing(false);
  }, [message.content]);

  const submitEdit = useCallback(async () => {
    if (!onEditAndResend || submitting) return;
    const trimmed = draft.trim();
    if (!trimmed) return;
    setSubmitting(true);
    try {
      await Promise.resolve(onEditAndResend(message.id, trimmed));
      setIsEditing(false);
    } finally {
      setSubmitting(false);
    }
  }, [draft, message.id, onEditAndResend, submitting]);

  const onTextareaKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        cancelEdit();
        return;
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        void submitEdit();
      }
    },
    [cancelEdit, submitEdit],
  );

  const editDisabled = !onEditAndResend || isStreaming;

  const contentSegments = useMemo(
    () => parseUserMessageRefs(message.content ?? ''),
    [message.content],
  );

  return (
    <article
      data-message-id={message.id}
      className={cn('group relative', className)}
      aria-label={t('chat.roleUserAria', { defaultValue: 'User message' })}
    >
      <div className="chat-role-label">
        <span
          className="chat-role-dot"
          style={{ background: 'rgb(var(--chat-text-tertiary) / 0.6)' }}
          aria-hidden
        />
        <span>{t('chat.roleUserShort', { defaultValue: 'You' })}</span>
        <span
          className="chat-msg-time normal-case font-normal tracking-normal tabular-nums"
          title={formatDate(message.createdAt)}
        >
          {formatDate(message.createdAt)}
        </span>
      </div>

      <div className="chat-user-card">
        {Array.isArray(message.attachments) && message.attachments.length > 0 && (
          <div className="flex flex-wrap items-start gap-2 mb-3">
            {message.attachments.map((attachment) => (
              <AttachmentCard key={attachment.id} attachment={attachment} />
            ))}
          </div>
        )}

        {isEditing ? (
          <div className="space-y-3">
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onTextareaKeyDown}
              rows={4}
              className={cn(
                'w-full min-h-[7.5rem] resize-y rounded-lg border border-border-subtle',
                'bg-background px-3 py-2.5 text-[15px] leading-relaxed text-foreground/95',
                'placeholder:text-muted-foreground-tertiary',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/25',
              )}
              aria-label={t('chat.editMessage', { defaultValue: 'Edit message' })}
            />
            <p className="text-xs text-muted-foreground-tertiary">
              {t('chat.inputFooterHint', {
                defaultValue: 'Enter to send · Shift+Enter for newline',
              })}
            </p>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                onClick={cancelEdit}
                disabled={submitting}
                className="px-3 py-1.5 text-sm rounded-md border border-border-subtle text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors disabled:opacity-50"
              >
                {t('common.cancel', { defaultValue: 'Cancel' })}
              </button>
              <Button
                type="button"
                size="sm"
                variant="primary"
                onClick={() => void submitEdit()}
                disabled={submitting || !draft.trim()}
              >
                {t('chat.editResend', { defaultValue: 'Send again' })}
              </Button>
            </div>
          </div>
        ) : (
          message.content && (
            <div className="text-[15px] leading-relaxed break-words text-foreground/95">
              {contentSegments.map((seg, idx) =>
                seg.type === 'text' ? (
                  <span key={idx} className="whitespace-pre-wrap">
                    {seg.value}
                  </span>
                ) : seg.type === 'knowledgeRef' ? (
                  <span
                    key={idx}
                    title={seg.raw}
                    className={cn(
                      'inline-flex align-middle max-w-[min(100%,20rem)] my-0.5',
                      'items-center gap-1.5 rounded-lg border border-border-subtle',
                      'bg-surface-sunken/60 px-2 py-0.5 text-xs',
                    )}
                  >
                    <span className="text-muted-foreground-tertiary flex-shrink-0">
                      <FileText className="w-3.5 h-3.5" aria-hidden />
                    </span>
                    <span
                      className={cn(
                        'flex-shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold tracking-tight',
                        'bg-primary-50 text-primary-800',
                        'dark:bg-primary-900/35 dark:text-primary-200',
                      )}
                    >
                      {t('chat.composerRefs.knowledgeBadge', {
                        defaultValue: 'Knowledge',
                      })}
                    </span>
                    <span className="min-w-0 truncate text-muted-foreground font-medium">
                      {seg.label}
                    </span>
                  </span>
                ) : seg.type === 'skillRef' ? (
                  <span
                    key={idx}
                    title={seg.raw}
                    className={cn(
                      'inline-flex align-middle max-w-[min(100%,20rem)] my-0.5',
                      'items-center gap-1.5 rounded-lg border border-border-subtle',
                      'bg-surface-sunken/60 px-2 py-0.5 text-xs',
                    )}
                  >
                    <span className="text-muted-foreground-tertiary flex-shrink-0">
                      <Puzzle className="w-3.5 h-3.5" aria-hidden />
                    </span>
                    <span
                      className={cn(
                        'flex-shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold tracking-tight',
                        'bg-violet-50 text-violet-900',
                        'dark:bg-violet-900/35 dark:text-violet-200',
                      )}
                    >
                      {t('chat.composerRefs.skillBadge', { defaultValue: 'Skill' })}
                    </span>
                    <span className="min-w-0 truncate text-muted-foreground font-medium">
                      {seg.label}
                    </span>
                  </span>
                ) : (
                  <span
                    key={idx}
                    title={seg.raw}
                    className={cn(
                      'inline-flex align-middle max-w-[min(100%,20rem)] my-0.5',
                      'items-center gap-1.5 rounded-lg border border-border-subtle',
                      'bg-surface-sunken/60 px-2 py-0.5 text-xs',
                    )}
                  >
                    <span className="text-muted-foreground-tertiary flex-shrink-0">
                      <FileText className="w-3.5 h-3.5" aria-hidden />
                    </span>
                    <span className="min-w-0 truncate text-muted-foreground font-medium">
                      {seg.label}
                    </span>
                  </span>
                ),
              )}
            </div>
          )
        )}
      </div>

      {!isEditing && !isStreaming && (message.content?.trim() || message.attachments?.length) ? (
        <div className="chat-msg-actions mt-2 flex flex-wrap items-center gap-0.5">
          {sessionId ? (
            <button
              type="button"
              onClick={() => void togglePinMessage(sessionId, message.id)}
              className={cn(
                'p-1.5 rounded-md text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors',
                isPinned && 'text-primary-600 dark:text-primary-400',
              )}
              aria-label={
                isPinned
                  ? t('chat.pins.unpin', { defaultValue: 'Unpin message' })
                  : t('chat.pins.pin', { defaultValue: 'Pin message' })
              }
              title={
                isPinned
                  ? t('chat.pins.unpin', { defaultValue: 'Unpin message' })
                  : t('chat.pins.pin', { defaultValue: 'Pin message' })
              }
            >
              <Pin
                className={cn('w-3.5 h-3.5', isPinned && 'fill-current')}
                aria-hidden
              />
            </button>
          ) : null}
          <button
            type="button"
            onClick={handleCopy}
            className="p-1.5 rounded-md text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors"
            aria-label={t('common.copy', { defaultValue: 'Copy' })}
            title={t('common.copy', { defaultValue: 'Copy' })}
          >
            {copied ? (
              <Check className="w-3.5 h-3.5 text-mint-500" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
          </button>
          {onEditAndResend && (
            <button
              type="button"
              onClick={startEdit}
              disabled={editDisabled}
              className={cn(
                'p-1.5 rounded-md text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors',
                editDisabled && 'opacity-40',
              )}
              aria-label={t('chat.edit', { defaultValue: 'Edit' })}
              title={
                isStreaming
                  ? t('chat.editDisabledStreaming', {
                      defaultValue: 'Wait for the reply to finish before editing.',
                    })
                  : t('chat.edit', { defaultValue: 'Edit' })
              }
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      ) : null}
    </article>
  );
}

UserMessageInner.displayName = 'UserMessage';

export const UserMessage = memo(UserMessageInner);
