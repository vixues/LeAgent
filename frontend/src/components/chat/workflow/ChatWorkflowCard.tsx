import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { GitBranch, ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Message } from '@/types/chat';
import { ChatWorkflowMiniGraph } from './ChatWorkflowMiniGraph';
import { ChatWorkflowStepRail } from './ChatWorkflowStepRail';
import { useWorkflowStepRunner } from './useWorkflowStepRunner';

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
  const [optionalOpen, setOptionalOpen] = useState(false);

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
          {t('chat.workflow.sessionFilesHint')}
        </p>
      </div>

      <div className="border-t border-border-subtle px-1 py-1">
        <button
          type="button"
          onClick={() => setOptionalOpen((o) => !o)}
          className="flex w-full items-center gap-1.5 rounded-lg px-2 py-2 text-left text-xs font-medium text-muted-foreground-tertiary hover:bg-surface-raised/60 hover:text-foreground transition-colors"
        >
          {optionalOpen ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0" aria-hidden />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0" aria-hidden />
          )}
          {t('chat.workflow.optionalInputToggle')}
        </button>
        {optionalOpen ? (
          <div className="px-2 pb-2">
            <label htmlFor={`wf-opt-${message.id}`} className="sr-only">
              {t('chat.workflow.optionalInputLabel')}
            </label>
            <textarea
              id={`wf-opt-${message.id}`}
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              rows={2}
              placeholder={t('chat.workflow.optionalInputPlaceholder')}
              className={cn(
                'w-full resize-y rounded-lg border border-border-subtle bg-surface-raised/80 px-2.5 py-2 text-xs text-foreground',
                'placeholder:text-muted-foreground-tertiary focus:outline-none focus:ring-2 focus:ring-primary-500/30',
              )}
            />
          </div>
        ) : null}
      </div>

      <ChatWorkflowStepRail
        steps={steps}
        stepRuns={wf.stepRuns}
        onRunStep={(stepId) => void runStep(message.id, stepId, wf.digest, userInput)}
      />
    </div>
  );
}
