import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CircleAlert, Images, Loader2, MessageCircleQuestion, SquareActivity } from 'lucide-react';

import { GenUiTreeView } from '@/components/canvas/GenUiRegistry';
import {
  listAssetHistoryTrees,
  listOrderedNodeAssets,
} from '@/components/canvas/genUi/genUiMedia';
import { cn } from '@/lib/utils';
import type { RunWorkflowActionPayload } from '@/lib/genUiActionBus';

import { blockedToGenUiTree } from '../genui/blockedToGenUiTree';
import { inputsToGenUiTree, type WorkflowInputSpec } from '../genui/inputsToGenUiTree';
import { outputsToGenUiTree, type WorkflowOutputSpec } from '../genui/outputsToGenUiTree';
import { useWorkflowGenUiBridge } from '../genui/useWorkflowGenUiBridge';
import { useExecutionOverlay } from '../store/executionOverlay';

export interface WorkflowRunPanelProps {
  flowId: string | null;
  /** Declared workflow inputs (drives the generated GenUI form). */
  inputs?: WorkflowInputSpec[] | null;
  /** Declared workflow outputs (render hints for results). */
  outputs?: WorkflowOutputSpec[] | null;
  /** Editor surfaces save the draft before running. */
  onBeforeRun?: (p: RunWorkflowActionPayload) => Promise<void> | void;
  onRunStarted?: (res: { prompt_id: string; execution_id: string }) => void;
  className?: string;
}

/**
 * GenUI-driven workflow I/O surface: the input form (ingress), live status,
 * pause/review interaction (control plane) and structured results (egress).
 * Shared between the graph editor's Run panel and the Playground.
 */
export function WorkflowRunPanel({
  flowId,
  inputs,
  outputs,
  onBeforeRun,
  onRunStarted,
  className,
}: WorkflowRunPanelProps) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);

  const promptId = useExecutionOverlay((s) => s.promptId);
  const running = useExecutionOverlay((s) => s.running);
  const blocked = useExecutionOverlay((s) => s.blocked);
  const resolvedOutputs = useExecutionOverlay((s) => s.outputs);
  const nodes = useExecutionOverlay((s) => s.nodes);
  const assetHistory = useExecutionOverlay((s) => s.assetHistory);
  const assetOrder = useExecutionOverlay((s) => s.assetOrder);
  const runErrors = useExecutionOverlay((s) => s.errors);

  useWorkflowGenUiBridge({
    inputs,
    onBeforeRun,
    onRunStarted: (res) => {
      setError(null);
      onRunStarted?.(res);
    },
    onError: setError,
  });

  const inputTree = useMemo(() => {
    if (!flowId) return null;
    return inputsToGenUiTree(inputs, {
      flowId,
      submitLabel: t('runPanel.run', 'Run'),
    });
  }, [flowId, inputs, t]);

  const blockedTree = useMemo(() => {
    if (!blocked || !promptId) return null;
    return blockedToGenUiTree(blocked, promptId, {
      answerPlaceholder: t('resume.answerPlaceholder', 'Type your answer...'),
      resume: t('resume.send', 'Resume'),
      approve: t('runPanel.approve', 'Approve'),
      reject: t('runPanel.reject', 'Reject'),
      commentsLabel: t('runPanel.comments', 'Comments'),
    });
  }, [blocked, promptId, t]);

  // Full iteration history when available; otherwise latest-only per node.
  const assetEntries = useMemo(() => {
    if (assetHistory.length > 0) {
      return listAssetHistoryTrees(assetHistory, undefined, t);
    }
    return listOrderedNodeAssets(nodes, assetOrder).map(({ nodeId, tree }) => ({
      id: nodeId,
      nodeId,
      tree,
    }));
  }, [assetHistory, nodes, assetOrder, t]);
  const assetCount = assetEntries.length;

  const outputTree = useMemo(() => {
    if (running || blocked) return null;
    return outputsToGenUiTree(resolvedOutputs, outputs, []);
  }, [running, blocked, resolvedOutputs, outputs]);

  return (
    <div className={cn('flex min-h-0 flex-col overflow-y-auto', className)}>
      {/* Ingress: generated input form */}
      <section className="border-b border-border">
        <header className="flex items-center gap-2 px-4 pt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t('runPanel.inputs', 'Inputs')}
        </header>
        {!flowId ? (
          <p className="px-4 py-3 text-xs text-muted-foreground">
            {t('runPanel.saveFirst', 'Save the workflow to enable runs.')}
          </p>
        ) : inputTree ? (
          <>
            <p className="px-4 pb-1 text-[11px] leading-relaxed text-muted-foreground">
              {t(
                'runPanel.inputsHint',
                'Set workflow inputs below, then click Run. Values are injected into nodes that reference ${input.name}.',
              )}
            </p>
            <GenUiTreeView tree={inputTree} />
          </>
        ) : (
          <p className="px-4 py-3 text-xs text-muted-foreground">
            {t(
              'runPanel.noInputs',
              'No workflow inputs declared. Add inputs under Inputs / Outputs, or edit prompt fields directly on nodes.',
            )}
          </p>
        )}
      </section>

      {error && (
        <div className="mx-4 mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
          <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {error}
        </div>
      )}

      {/* Status */}
      {running && (
        <div className="flex items-center gap-2 px-4 py-3 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary-500" />
          {t('runPanel.running', 'Running...')}
        </div>
      )}

      {/* Control plane: pause / review interaction */}
      {blockedTree && (
        <section className="border-b border-border">
          <header className="flex items-center gap-2 px-4 pt-3 text-xs font-semibold uppercase tracking-wide text-amber-600 dark:text-amber-400">
            <MessageCircleQuestion className="h-3.5 w-3.5" />
            {t('runPanel.waiting', 'Waiting for your input')}
          </header>
          <GenUiTreeView tree={blockedTree} />
        </section>
      )}

      {/* Egress: generated asset gallery (image / video / 3D) */}
      {assetEntries.length > 0 && !blocked && (
        <section className="border-b border-border">
          <header className="flex items-center gap-2 px-4 pt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <Images className="h-3.5 w-3.5" />
            {t('runPanel.assets', 'Assets')}
            {assetCount > 0 && (
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                {assetCount}
              </span>
            )}
          </header>
          {assetEntries.map(({ id, tree }) => (
            <GenUiTreeView key={id} tree={tree} />
          ))}
        </section>
      )}

      {/* Egress: structured results */}
      {outputTree && (
        <section>
          <header className="flex items-center gap-2 px-4 pt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <SquareActivity className="h-3.5 w-3.5" />
            {t('runPanel.results', 'Results')}
          </header>
          <GenUiTreeView tree={outputTree} />
        </section>
      )}

      {runErrors.length > 0 && !running && (
        <section className="px-4 py-3">
          {runErrors.map((e, i) => (
            <p key={i} className="text-xs text-red-600 dark:text-red-400">
              {e}
            </p>
          ))}
        </section>
      )}
    </div>
  );
}
