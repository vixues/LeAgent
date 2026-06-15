import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { GitBranch, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Message } from '@/types/chat';
import { ChatWorkflowMiniGraph } from './ChatWorkflowMiniGraph';
import { ChatWorkflowInputPanel } from './ChatWorkflowInputPanel';
import { ChatWorkflowStepRail } from './ChatWorkflowStepRail';
import { useWorkflowStepOverlaySync } from './useWorkflowStepOverlaySync';
import { useWorkflowStepRunner } from './useWorkflowStepRunner';
import { workflowNeedsFileInput } from './workflowStepUtils';

interface ChatWorkflowCardProps {
  message: Message;
  sessionId: string;
  className?: string;
}

export function ChatWorkflowCard({ message, sessionId, className }: ChatWorkflowCardProps) {
  const { t } = useTranslation();
  const embed = message.workflowEmbed;
  const wf = message.workflow;
  const { runStep } = useWorkflowStepRunner(sessionId);
  const [userInput, setUserInput] = useState('');
  const needsFileInput = wf ? workflowNeedsFileInput(wf.spec.steps) : false;

  useWorkflowStepOverlaySync(sessionId, message.id);

  if (embed) {
    const dataName =
      typeof embed.data.name === 'string' && embed.data.name.trim()
        ? embed.data.name.trim()
        : undefined;
    const title = embed.title || dataName || t('chat.workflow.embedFallbackTitle');
    return (
      <div
        className={cn(
          'rounded-xl border border-border-subtle bg-surface-sunken/40 shadow-soft mb-3 overflow-hidden',
          className,
        )}
        role="region"
        aria-label={t('chat.workflow.embedCardAria', { title })}
      >
        <div className="px-3 pt-3 pb-2">
          <div className="flex items-start gap-2.5">
            <GitBranch
              className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground-tertiary"
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-semibold text-foreground leading-snug">{title}</h3>
              {embed.summary ? (
                <p className="text-xs text-muted-foreground-tertiary mt-1 line-clamp-2 leading-relaxed">
                  {embed.summary}
                </p>
              ) : null}
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground-tertiary mt-2 pl-[1.375rem] leading-snug">
            {t('chat.workflow.sessionFilesHint')}
          </p>
          {embed.flowId ? (
            <div className="mt-2 pl-[1.375rem]">
              <Link
                to={`/workflows/${embed.flowId}`}
                className="inline-flex items-center gap-1 text-xs font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300"
              >
                <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                {t('chat.workflow.openInEditor')}
              </Link>
            </div>
          ) : null}
        </div>
        <div className="chat-workflow-surface border-t border-border-subtle px-2 pb-3 pt-2">
          <p className="mb-1.5 px-0.5 text-[10px] leading-snug text-muted-foreground-tertiary">
            {t('chat.workflow.embedPreviewNote')}
          </p>
          <ChatWorkflowMiniGraph flowData={embed.data} previewTitle={title} />
        </div>
        <p className="px-3 pb-2 text-[10px] font-mono text-muted-foreground-tertiary/80 truncate">
          {embed.digest.slice(0, 16)}…
        </p>
      </div>
    );
  }

  if (!wf) return null;

  const steps = wf.spec.steps;

  return (
    <div
      className={cn(
        'rounded-xl border border-border-subtle bg-surface-sunken/40 shadow-soft mb-3 overflow-hidden',
        className,
      )}
      role="region"
      aria-label={t('chat.workflow.cardAria', { title: wf.spec.title })}
    >
      <div className="px-3 pt-3 pb-2">
        <div className="flex items-start gap-2.5">
          <GitBranch
            className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground-tertiary"
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-foreground leading-snug">{wf.spec.title}</h3>
            {wf.spec.summary ? (
              <p className="text-xs text-muted-foreground-tertiary mt-1 line-clamp-2 leading-relaxed">
                {wf.spec.summary}
              </p>
            ) : null}
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground-tertiary mt-2 pl-[1.375rem] leading-snug">
          {needsFileInput
            ? t('chat.workflow.sessionFilesHintCsv')
            : t('chat.workflow.sessionFilesHint')}
        </p>
      </div>

      <ChatWorkflowInputPanel
        sessionId={sessionId}
        value={userInput}
        onChange={setUserInput}
        needsFileInput={needsFileInput}
      />

      <ChatWorkflowStepRail
        steps={steps}
        stepRuns={wf.stepRuns}
        onRunStep={(stepId) => void runStep(message.id, stepId, wf.digest, userInput)}
      />
    </div>
  );
}
