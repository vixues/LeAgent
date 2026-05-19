import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Pin, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chat';

function scrollToMessage(messageId: string) {
  const safe =
    typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
      ? CSS.escape(messageId)
      : messageId.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  const el = document.querySelector(`[data-message-id="${safe}"]`);
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

/**
 * Sticky session pin bar: chips for server-backed pins; click scrolls, X removes.
 */
export function ChatPinnedStrip({ className }: { className?: string }) {
  const { t } = useTranslation();
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const sessions = useChatStore((s) => s.sessions);
  const messagesMap = useChatStore((s) => s.messages);
  const togglePinMessage = useChatStore((s) => s.togglePinMessage);

  const session = currentSessionId ? sessions.find((s) => s.id === currentSessionId) : undefined;
  const pins = session?.pinnedMessageIds ?? [];
  const messages = currentSessionId ? messagesMap[currentSessionId] ?? [] : [];

  const previewFor = useCallback(
    (messageId: string) => {
      const msg = messages.find((m) => m.id === messageId);
      if (!msg) {
        return t('chat.pins.missingMessage', { defaultValue: 'Message' });
      }
      const raw = (msg.content ?? '').trim().replace(/\s+/g, ' ');
      if (raw.length > 0) {
        return raw.length > 72 ? `${raw.slice(0, 72)}…` : raw;
      }
      if (msg.attachments?.length) {
        return t('chat.pins.attachmentOnly', { defaultValue: 'Attachment' });
      }
      return msg.role === 'user'
        ? t('chat.roleUserShort', { defaultValue: 'You' })
        : t('chat.roleAssistantShort', { defaultValue: 'Assistant' });
    },
    [messages, t],
  );

  if (!currentSessionId || pins.length === 0) return null;

  return (
    <div
      className={cn(
        'flex-shrink-0 border-b border-border-subtle bg-surface/80 backdrop-blur-sm',
        className,
      )}
    >
      <div className="mx-auto flex max-w-[72ch] items-center gap-2 pl-20 pr-6 py-1.5">
        <Pin className="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground" aria-hidden />
        <span className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground whitespace-nowrap">
          {t('chat.pins.barLabel', { defaultValue: 'Pinned' })}
        </span>
        <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto">
          {pins.map((id) => (
            <div
              key={id}
              className="inline-flex max-w-[min(100%,14rem)] flex-shrink-0 items-center gap-0.5 rounded-full border border-border-subtle bg-surface-sunken/60 px-2 py-0.5 text-xs text-foreground/90"
            >
              <button
                type="button"
                onClick={() => scrollToMessage(id)}
                className="min-w-0 truncate text-left hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
                title={t('chat.pins.scrollTo', { defaultValue: 'Jump to message' })}
              >
                {previewFor(id)}
              </button>
              <button
                type="button"
                onClick={() => void togglePinMessage(currentSessionId, id)}
                className="flex-shrink-0 rounded p-0.5 text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken"
                aria-label={t('chat.pins.unpin', { defaultValue: 'Unpin message' })}
                title={t('chat.pins.unpin', { defaultValue: 'Unpin message' })}
              >
                <X className="w-3 h-3" aria-hidden />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
