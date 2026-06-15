import { useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Play, Loader2, Check, AlertCircle, Circle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useExecutionStream } from '@/features/workflow/api/useExecutionStream';
import { useExecutionOverlay } from '@/features/workflow/store/executionOverlay';
import type { ChatWorkflowStepModel, ChatWorkflowStepRunRecord } from '@/types/chat';

export interface ChatWorkflowStepRailProps {
  steps: ChatWorkflowStepModel[];
  stepRuns: Record<string, ChatWorkflowStepRunRecord>;
  onRunStep: (stepId: string) => void;
}

function StepConnector() {
  return (
    <div
      className="flex h-full min-h-[140px] w-10 shrink-0 items-center justify-center px-0.5"
      aria-hidden
    >
      <div className="relative flex w-full items-center justify-center">
        <div className="h-px w-full bg-gradient-to-r from-border-subtle via-border to-border-subtle" />
        <svg
          className="absolute right-0 h-2 w-2 translate-x-0.5 text-muted-foreground-tertiary/70"
          viewBox="0 0 8 8"
          aria-hidden
        >
          <path d="M0 0 L8 4 L0 8 Z" fill="currentColor" />
        </svg>
      </div>
    </div>
  );
}

function useHorizontalWheelScroll() {
  const ref = useRef<HTMLDivElement>(null);
  const onWheel = useCallback((e: React.WheelEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (!el) return;
    const { scrollLeft, scrollWidth, clientWidth } = el;
    if (scrollWidth <= clientWidth) return;
    const raw = e.deltaY !== 0 ? e.deltaY : e.deltaX;
    const delta = e.deltaMode === 1 ? raw * 16 : raw;
    const atStart = scrollLeft <= 0 && delta < 0;
    const atEnd = scrollLeft + clientWidth >= scrollWidth - 1 && delta > 0;
    if (atStart || atEnd) return;
    e.preventDefault();
    const nextLeft = scrollLeft + delta;
    el.scrollLeft = Math.max(0, Math.min(nextLeft, scrollWidth - clientWidth));
  }, []);
  return { ref, onWheel };
}

function StepLiveDetail({ promptId }: { promptId: string }) {
  const { t } = useTranslation();
  useExecutionStream(promptId);
  const overlay = useExecutionOverlay((s) => s.overlays[promptId]);
  const runningCount = Object.values(overlay?.nodes ?? {}).filter((n) => n.status === 'running').length;

  if (overlay?.blocked) {
    return (
      <p className="mt-1 text-[10px] text-amber-700 dark:text-amber-300">
        {t('chat.execution.panel.workflowBlocked')}
      </p>
    );
  }

  if (overlay?.running && runningCount > 0) {
    return (
      <p className="mt-1 text-[10px] text-primary-700 dark:text-primary-300">
        {t('chat.execution.panel.liveNodes', { count: runningCount })}
      </p>
    );
  }

  return null;
}

function resolveStepVisualState(run: ChatWorkflowStepRunRecord) {
  const promptId = run.prompt_id;
  const overlay = promptId ? useExecutionOverlay.getState().overlays[promptId] : undefined;
  const liveRunning = Boolean(promptId && overlay?.running);
  const liveBlocked = Boolean(overlay?.blocked);
  const overlayTerminal = Boolean(promptId) && !liveRunning && !liveBlocked;
  const overlayErrorCount = overlay?.errors.length ?? 0;
  const staleRunning =
    run.status === 'running' && Boolean(promptId) && overlayTerminal && overlayErrorCount === 0;
  const effectiveStatus = staleRunning ? ('idle' as const) : run.status;
  const isError =
    effectiveStatus === 'error' || (overlayTerminal && overlayErrorCount > 0);
  const isSuccess =
    !isError &&
    (effectiveStatus === 'success' ||
      (effectiveStatus === 'running' && overlayTerminal && overlayErrorCount === 0));
  const isRunning =
    !isError &&
    effectiveStatus !== 'success' &&
    (effectiveStatus === 'running' || liveRunning || liveBlocked);
  const isIdle = !isRunning && !isSuccess && !isError;

  return { isRunning, isSuccess, isError, isIdle, promptId };
}

function WorkflowStepCard({
  step,
  index,
  run,
  onRunStep,
}: {
  step: ChatWorkflowStepModel;
  index: number;
  run: ChatWorkflowStepRunRecord;
  onRunStep: (stepId: string) => void;
}) {
  const { t } = useTranslation();
  const promptId = run.prompt_id;
  const overlayRunning = useExecutionOverlay((s) =>
    promptId ? Boolean(s.overlays[promptId]?.running) : false,
  );
  const overlayBlocked = useExecutionOverlay((s) =>
    promptId ? Boolean(s.overlays[promptId]?.blocked) : false,
  );

  const overlayErrorCount = useExecutionOverlay((s) =>
    promptId ? (s.overlays[promptId]?.errors.length ?? 0) : 0,
  );

  const overlayTerminal =
    Boolean(promptId) && !overlayRunning && !overlayBlocked;
  const staleRunning =
    run.status === 'running' && Boolean(promptId) && overlayTerminal && overlayErrorCount === 0;
  const effectiveStatus = staleRunning ? ('idle' as const) : run.status;
  const isError =
    effectiveStatus === 'error' || (overlayTerminal && overlayErrorCount > 0);
  const isSuccess =
    !isError &&
    (effectiveStatus === 'success' ||
      (effectiveStatus === 'running' && overlayTerminal && overlayErrorCount === 0));
  const isRunning =
    !isError &&
    effectiveStatus !== 'success' &&
    (effectiveStatus === 'running' || overlayRunning || overlayBlocked);
  const isIdle =
    effectiveStatus === 'idle' && !overlayRunning && !overlayBlocked && !isError;
  const showLiveDetail = run.status === 'running' && Boolean(promptId);

  return (
    <div className="flex flex-nowrap items-stretch">
      {index > 0 ? <StepConnector /> : null}
      <div
        role="listitem"
        className={cn(
          'flex w-[min(280px,calc(100vw-6rem))] min-w-[220px] shrink-0 flex-col rounded-2xl border bg-surface-raised/90 px-3 py-3 shadow-soft',
          'transition-[box-shadow,border-color] duration-200',
          isRunning &&
            'border-primary-400/50 shadow-[0_0_0_1px_rgba(14,165,233,0.25)] motion-safe:animate-pulse-slow',
          isSuccess && 'border-mint-200/80 dark:border-mint-800/50',
          isError && 'border-red-200/90 dark:border-red-900/50',
          isIdle && 'border-border-subtle',
        )}
      >
        <div className="flex items-start gap-2 border-b border-border-subtle/80 pb-2">
          <span
            className="mt-0.5 inline-flex h-6 min-w-[1.5rem] items-center justify-center rounded-md bg-surface-sunken/80 px-1 text-[10px] font-mono tabular-nums text-muted-foreground-tertiary"
            aria-hidden
          >
            {String(index + 1).padStart(2, '0')}
          </span>
          <h4 className="min-w-0 flex-1 text-sm font-medium leading-snug text-foreground">
            {step.label}
          </h4>
        </div>
        {step.hint ? (
          <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground-tertiary">
            {step.hint}
          </p>
        ) : null}

        <div className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground-tertiary">
          {isRunning ? (
            <>
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary-600 dark:text-primary-400" />
              <span className="text-primary-700 dark:text-primary-300">
                {overlayBlocked
                  ? t('chat.execution.panel.workflowBlocked')
                  : t('chat.workflow.running')}
              </span>
            </>
          ) : null}
          {isSuccess ? (
            <>
              <Check className="h-3.5 w-3.5 shrink-0 text-mint-600 dark:text-mint-400" aria-hidden />
              <span className="text-mint-700 dark:text-mint-400">{t('chat.workflow.done')}</span>
            </>
          ) : null}
          {isError ? (
            <>
              <AlertCircle className="h-3.5 w-3.5 shrink-0 text-red-600 dark:text-red-400" aria-hidden />
              <span className="text-red-600 dark:text-red-400">{t('chat.workflow.runFailed')}</span>
            </>
          ) : null}
          {isIdle ? (
            <>
              <Circle className="h-3 w-3 shrink-0 text-muted-foreground-tertiary" strokeWidth={2} />
              <span>{t('chat.workflow.statusIdle')}</span>
            </>
          ) : null}
        </div>

        {showLiveDetail ? <StepLiveDetail promptId={promptId!} /> : null}

        {isError && run.error ? (
          <p className="mt-1.5 flex items-start gap-1 text-xs leading-snug text-red-600 dark:text-red-400">
            <AlertCircle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
            <span className="min-w-0 break-words">{run.error}</span>
          </p>
        ) : null}

        <details className="mt-2 group/details border-t border-border-subtle/60 pt-2">
          <summary className="cursor-pointer list-none text-[11px] text-muted-foreground-tertiary hover:text-foreground [&::-webkit-details-marker]:hidden">
            <span className="underline-offset-2 group-open/details:underline">
              {t('chat.workflow.stepDetails')}
            </span>
          </summary>
          <p className="mt-1 break-all font-mono text-[10px] text-muted-foreground-tertiary">
            {step.action.tool_id}
          </p>
          {promptId ? (
            <p className="mt-0.5 break-all font-mono text-[10px] text-muted-foreground-tertiary/80">
              {promptId}
            </p>
          ) : null}
        </details>

        <div className="mt-3 flex flex-1 flex-col justify-end">
          <button
            type="button"
            disabled={isRunning}
            aria-busy={isRunning}
            onClick={() => void onRunStep(step.id)}
            className={cn(
              'inline-flex min-h-9 w-full items-center justify-center gap-1.5 rounded-xl border border-border-subtle',
              'bg-surface/90 px-3 text-xs font-medium text-foreground',
              'hover:bg-surface-hover hover:border-border-strong transition-colors',
              'disabled:pointer-events-none disabled:opacity-50',
              'focus:outline-none focus:ring-2 focus:ring-primary-500/30',
            )}
          >
            {isRunning ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                {t('chat.workflow.running')}
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5" aria-hidden />
                {isSuccess ? t('chat.workflow.rerun') : t('chat.workflow.run')}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export function ChatWorkflowStepRail({ steps, stepRuns, onRunStep }: ChatWorkflowStepRailProps) {
  const { t } = useTranslation();
  const { ref: scrollRef, onWheel } = useHorizontalWheelScroll();

  const progressSummary = steps
    .map((s) => {
      const run = stepRuns[s.id] ?? { status: 'idle' as const };
      const visual = resolveStepVisualState(run);
      const st = visual.isRunning
        ? 'running'
        : visual.isSuccess
          ? 'success'
          : visual.isError
            ? 'error'
            : 'idle';
      return `${s.label}: ${st}`;
    })
    .join('; ');

  return (
    <div className="chat-workflow-surface border-t border-border-subtle bg-surface-raised/20">
      <div
        ref={scrollRef}
        onWheel={onWheel}
        className="overflow-x-auto overflow-y-hidden overscroll-x-contain px-2 py-3"
        tabIndex={0}
        role="list"
        aria-label={t('chat.workflow.stepsRailAria', { summary: progressSummary })}
      >
        <div className="flex min-w-min flex-nowrap items-stretch">
          {steps.map((step, index) => (
            <WorkflowStepCard
              key={step.id}
              step={step}
              index={index}
              run={stepRuns[step.id] ?? { status: 'idle' }}
              onRunStep={onRunStep}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
