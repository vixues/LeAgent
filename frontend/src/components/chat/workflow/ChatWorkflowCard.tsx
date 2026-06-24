import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { AlertCircle, CheckCircle2, ExternalLink, GitBranch } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Message } from '@/types/chat';
import { useExecutionStream } from '@/features/workflow/api/useExecutionStream';
import { WorkflowOperationPanel } from '@/features/workflow/components/WorkflowOperationPanel';
import { useGenUiFormsStore } from '@/stores/genUiForms';
import { ChatWorkflowMiniGraph } from './ChatWorkflowMiniGraph';
import { ChatWorkflowStepRail } from './ChatWorkflowStepRail';
import {
  CHAT_USER_INPUT_FIELD,
  embedInputSpecs,
  synthesizedUserInputSpec,
  useSessionAttachments,
} from './chatWorkflowInputs';
import { useWorkflowStepOverlaySync } from './useWorkflowStepOverlaySync';
import { useWorkflowStepRunner } from './useWorkflowStepRunner';
import { useWorkflowEmbedOverlaySync } from './useWorkflowEmbedOverlaySync';
import { workflowNeedsFileInput } from './workflowStepUtils';

interface ChatWorkflowCardProps {
  message: Message;
  sessionId: string;
  className?: string;
}

export function ChatWorkflowCard({ message, sessionId, className }: ChatWorkflowCardProps) {
  const embed = message.workflowEmbed;
  const wf = message.workflow;
  const { runStep } = useWorkflowStepRunner(sessionId);

  // Hooks must run unconditionally; both cards can coexist on one message.
  useWorkflowStepOverlaySync(sessionId, message.id);
  useWorkflowEmbedOverlaySync(sessionId, message.id);
  useExecutionStream(embed?.run?.promptId ?? null);

  if (!embed && !wf) return null;

  return (
    <>
      {embed ? (
        <EmbedCard
          embed={embed}
          sessionId={sessionId}
          messageId={message.id}
          className={className}
        />
      ) : null}
      {wf ? (
        <StepCard
          wf={wf}
          sessionId={sessionId}
          messageId={message.id}
          className={className}
          onRunStep={(stepId, userInput) =>
            void runStep(message.id, stepId, wf.digest, userInput)
          }
        />
      ) : null}
    </>
  );
}

const CARD_CLASS =
  'rounded-xl border border-border-subtle bg-surface-sunken/40 shadow-soft mb-3 overflow-hidden';

function EmbedCard({
  embed,
  sessionId,
  messageId,
  className,
}: {
  embed: NonNullable<Message['workflowEmbed']>;
  sessionId: string;
  messageId: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const attachments = useSessionAttachments(sessionId);
  const runStatus = embed.run?.status ?? 'idle';
  const isRunning = runStatus === 'running';
  const runPromptId = embed.run?.promptId ?? null;
  const dataName =
    typeof embed.data.name === 'string' && embed.data.name.trim()
      ? embed.data.name.trim()
      : undefined;
  const title = embed.title || dataName || t('chat.workflow.embedFallbackTitle');

  const inputs = useMemo(
    () =>
      embedInputSpecs(
        embed.data,
        synthesizedUserInputSpec({
          attachments,
          needsFileInput: false,
          label: t('chat.workflow.inputPanelTitle'),
          description: t('chat.workflow.inputPanelDescription'),
        }),
      ),
    [embed.data, attachments, t],
  );

  const header = (
    <div className="px-3 pt-3 pb-2">
      <div className="flex items-start gap-2.5 pr-7">
        <GitBranch className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground-tertiary" aria-hidden />
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
      <div className="mt-2 flex flex-wrap items-center gap-2 pl-[1.375rem]">
        {runStatus === 'success' ? (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
            {t('chat.workflow.done')}
          </span>
        ) : null}
        {runStatus === 'error' ? (
          <span
            className="inline-flex items-center gap-1 text-xs font-medium text-rose-600 dark:text-rose-400"
            title={embed.run?.error}
          >
            <AlertCircle className="h-3.5 w-3.5" aria-hidden />
            {t('chat.workflow.runFailed')}
          </span>
        ) : null}
        {embed.flowId ? (
          <Link
            to={`/workflows/${embed.flowId}`}
            className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300"
          >
            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            {t('chat.workflow.openInEditor')}
          </Link>
        ) : null}
      </div>
    </div>
  );

  const slot = (
    <div className="chat-workflow-surface px-2 pb-3 pt-2">
      <p className="mb-1.5 px-0.5 text-[10px] leading-snug text-muted-foreground-tertiary">
        {isRunning ? t('chat.workflow.embedRunningNote') : t('chat.workflow.embedPreviewNote')}
      </p>
      <ChatWorkflowMiniGraph
        flowData={embed.data}
        previewTitle={title}
        runPromptId={runPromptId}
        digest={embed.digest}
      />
    </div>
  );

  return (
    <div
      className={cn(CARD_CLASS, className)}
      role="region"
      aria-label={t('chat.workflow.embedCardAria', { title })}
    >
      <WorkflowOperationPanel
        flowId={embed.flowId ?? null}
        inputs={inputs}
        overlaySource={runPromptId}
        runTarget={{ kind: 'chat_embed', sessionId, messageId, digest: embed.digest }}
        formId={`chat-workflow-embed-${messageId}`}
        sessionId={sessionId}
        messageId={messageId}
        submitLabel={runStatus === 'idle' ? t('chat.workflow.run') : t('chat.workflow.rerun')}
        header={header}
        slot={slot}
        error={runStatus === 'error' ? embed.run?.error ?? t('chat.workflow.runFailed') : null}
        compact
        brandMark
      />
    </div>
  );
}

function StepCard({
  wf,
  sessionId,
  messageId,
  className,
  onRunStep,
}: {
  wf: NonNullable<Message['workflow']>;
  sessionId: string;
  messageId: string;
  className?: string;
  onRunStep: (stepId: string, userInput: string) => void;
}) {
  const { t } = useTranslation();
  const needsFileInput = workflowNeedsFileInput(wf.spec.steps);
  const attachments = useSessionAttachments(sessionId);
  const formId = `chat-workflow-step-${messageId}`;

  const userInput = useGenUiFormsStore((s) => {
    const v = s.values[`${sessionId}::${messageId}::${formId}`]?.[CHAT_USER_INPUT_FIELD];
    return typeof v === 'string' ? v : '';
  });

  const inputs = useMemo(
    () => [
      synthesizedUserInputSpec({
        attachments,
        needsFileInput,
        label: needsFileInput
          ? t('chat.workflow.inlineInputTitleFile')
          : t('chat.workflow.inlineInputTitle'),
        description: needsFileInput
          ? t('chat.workflow.inlineInputHintFile')
          : t('chat.workflow.inlineInputHint'),
      }),
    ],
    [attachments, needsFileInput, t],
  );

  const header = (
    <div className="px-3 pt-3 pb-2">
      <div className="flex items-start gap-2.5 pr-7">
        <GitBranch className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground-tertiary" aria-hidden />
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
  );

  return (
    <div
      className={cn(CARD_CLASS, className)}
      role="region"
      aria-label={t('chat.workflow.cardAria', { title: wf.spec.title })}
    >
      <WorkflowOperationPanel
        flowId={null}
        inputs={inputs}
        overlaySource={null}
        runTarget={{ kind: 'chat_step', sessionId, messageId, digest: wf.digest }}
        formId={formId}
        sessionId={sessionId}
        messageId={messageId}
        includeSubmit={false}
        header={header}
        compact
        brandMark
      />

      <ChatWorkflowStepRail
        steps={wf.spec.steps}
        stepRuns={wf.stepRuns}
        onRunStep={(stepId) => onRunStep(stepId, userInput)}
      />
    </div>
  );
}
