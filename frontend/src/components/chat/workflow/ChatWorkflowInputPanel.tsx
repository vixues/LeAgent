import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import { FileText, Image, Paperclip } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chat';
import type { Attachment } from '@/types/chat';

interface ChatWorkflowInputPanelProps {
  sessionId: string;
  value: string;
  onChange: (value: string) => void;
  needsFileInput: boolean;
}

function attachmentPath(att: Attachment): string {
  if (att.localPath?.trim()) return att.localPath.trim();
  return att.name;
}

function AttachmentIcon({ type }: { type: string }) {
  if (type.startsWith('image/')) {
    return <Image className="h-3.5 w-3.5 shrink-0 text-primary-600 dark:text-primary-400" aria-hidden />;
  }
  return <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground-tertiary" aria-hidden />;
}

export function ChatWorkflowInputPanel({
  sessionId,
  value,
  onChange,
  needsFileInput,
}: ChatWorkflowInputPanelProps) {
  const { t } = useTranslation();

  const attachments = useChatStore(
    useShallow((s) => {
      const messages = s.messages[sessionId] ?? [];
      const seen = new Set<string>();
      const out: Attachment[] = [];
      for (const msg of messages) {
        for (const att of msg.attachments ?? []) {
          if (!att.id || seen.has(att.id)) continue;
          seen.add(att.id);
          out.push(att);
        }
      }
      return out;
    }),
  );

  const trimmed = value.trim();
  const selectedAttachmentId =
    attachments.find((att) => attachmentPath(att) === trimmed)?.id ?? null;

  return (
    <div className="border-t border-border-subtle bg-surface-raised/15 px-3 py-3">
      <div className="mb-2 flex items-center gap-2">
        <Paperclip className="h-3.5 w-3.5 shrink-0 text-muted-foreground-tertiary" aria-hidden />
        <span className="text-xs font-medium text-foreground">
          {needsFileInput
            ? t('chat.workflow.inlineInputTitleFile')
            : t('chat.workflow.inlineInputTitle')}
        </span>
      </div>

      <label htmlFor={`wf-input-${sessionId}`} className="sr-only">
        {t('chat.workflow.paramSettingsPathLabel')}
      </label>
      <Input
        id={`wf-input-${sessionId}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={
          needsFileInput
            ? t('chat.workflow.paramSettingsPathPlaceholderFile')
            : t('chat.workflow.paramSettingsPathPlaceholder')
        }
        className="font-mono text-xs"
      />

      <div className="mt-2.5">
        <p className="mb-1.5 text-[11px] font-medium text-muted-foreground-tertiary">
          {t('chat.workflow.paramSettingsAttachments')}
        </p>
        {attachments.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border-subtle px-2.5 py-2 text-[11px] text-muted-foreground-tertiary">
            {t('chat.workflow.paramSettingsAttachmentsEmpty')}
          </p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {attachments.map((att) => {
              const path = attachmentPath(att);
              const selected = selectedAttachmentId === att.id;
              return (
                <button
                  key={att.id}
                  type="button"
                  onClick={() => onChange(path)}
                  className={cn(
                    'inline-flex max-w-full items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-left text-[11px]',
                    'transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500/30',
                    selected
                      ? 'border-primary-400/60 bg-primary-500/10 text-primary-800 dark:text-primary-200'
                      : 'border-border-subtle bg-surface-raised/70 text-foreground hover:border-border-strong hover:bg-surface-raised',
                  )}
                  title={path}
                >
                  <AttachmentIcon type={att.type} />
                  <span className="truncate font-medium">{att.name}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <p className="mt-2 text-[10px] leading-snug text-muted-foreground-tertiary">
        {needsFileInput
          ? t('chat.workflow.inlineInputHintFile')
          : t('chat.workflow.inlineInputHint')}
      </p>
    </div>
  );
}
