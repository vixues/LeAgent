import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { CodeBlock } from '@/components/common/CodeBlock';
import { findActiveDocProcessorStream } from '@/lib/docProcessorStreamPreview';
import { EMPTY_MESSAGE_LIST } from '@/lib/emptyChatMessages';
import { useChatStore } from '@/stores/chat';

/**
 * Live preview of ``text_processor`` / ``markdown_processor`` write streams
 * in the workspace Files tab (fed by SSE ``tool_call_delta``).
 */
export function DocGenerationLivePreview() {
  const { t } = useTranslation();
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const messages = useChatStore((s) =>
    currentSessionId ? s.messages[currentSessionId] ?? EMPTY_MESSAGE_LIST : EMPTY_MESSAGE_LIST,
  );

  const active = findActiveDocProcessorStream(messages);
  if (!active) return null;

  const lineCount = active.previewText ? active.previewText.split('\n').length : 0;

  return (
    <div className="flex flex-col rounded-lg border border-primary/25 bg-primary/[0.04] overflow-hidden mb-2">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-primary/15">
        <Loader2 className="size-3 shrink-0 animate-spin text-primary" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-primary/90">
            {t('chat.workspace.files.docStreamTitle', {
              defaultValue: 'Generating document (live)',
            })}
          </p>
          {active.filePath ? (
            <p className="truncate font-mono text-[10px] text-muted-foreground" title={active.filePath}>
              {active.filePath}
            </p>
          ) : null}
        </div>
        <span className="text-[10px] tabular-nums text-muted-foreground/70 shrink-0">
          {lineCount} {lineCount === 1 ? 'line' : 'lines'}
        </span>
      </div>
      <div className="max-h-[40vh] overflow-auto">
        <CodeBlock
          code={active.previewText || '…'}
          language={active.language}
          showLineNumbers={false}
          showLanguage={false}
          showCopyButton
          className="border-0 rounded-none text-[11px]"
        />
      </div>
    </div>
  );
}
