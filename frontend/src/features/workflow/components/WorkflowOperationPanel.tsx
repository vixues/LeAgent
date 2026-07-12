import { type ReactNode, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { CircleAlert, Images, Loader2, MessageCircleQuestion, SquareActivity } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';

import { GenUiTreeView } from '@/components/canvas/GenUiRegistry';
import {
  listAssetHistoryTrees,
  listOrderedNodeAssets,
} from '@/components/canvas/genUi/genUiMedia';
import { AppLogo } from '@/components/brand/AppLogo';
import { cn } from '@/lib/utils';

import { blockedToGenUiTree } from '../genui/blockedToGenUiTree';
import { type WorkflowInputSpec } from '../genui/inputsToGenUiTree';
import { outputsToGenUiTree, type WorkflowOutputSpec } from '../genui/outputsToGenUiTree';
import { useExecutionOverlay, type PromptOverlayState } from '../store/executionOverlay';
import { WorkflowInputPanel } from './WorkflowInputPanel';
import type { Attachment } from '@/types/chat';

/** Where the generated run form should dispatch its run. */
export type OperationRunTarget =
  | { kind: 'flow' }
  | { kind: 'chat_embed'; sessionId: string; messageId: string; digest: string }
  | { kind: 'chat_step'; sessionId: string; messageId: string; digest: string; stepId?: string };

export interface WorkflowOperationPanelProps {
  /** Saved Flow id (empty/null for unsaved chat embeds). */
  flowId: string | null;
  /** Declared workflow inputs (drives the generated GenUI form). */
  inputs?: WorkflowInputSpec[] | null;
  /** Declared workflow outputs (render hints for results). */
  outputs?: WorkflowOutputSpec[] | null;
  /**
   * Overlay source. When ``'editor'`` the panel reads the editor-synced
   * singleton; otherwise it reads ``overlays[promptId]`` for a specific run
   * (chat surfaces, which never repoint the editor singleton).
   */
  overlaySource?: 'editor' | string | null;
  /** Routing target for the run form's submit button. */
  runTarget?: OperationRunTarget;
  /** Stable form id (message-scoped on chat surfaces). */
  formId?: string;
  /** Render context for GenUI form scoping + action dispatch. */
  sessionId?: string;
  messageId?: string;
  /** Chat session attachments for file / user_input pickers. */
  attachments?: Attachment[];
  /** Whether the run form appends a submit button (default true). */
  includeSubmit?: boolean;
  submitLabel?: string;
  /** Localized helper text under the inputs header. */
  inputsHint?: string;
  /** Message shown when no inputs are declared and none synthesized. */
  emptyInputsMessage?: string;
  /** Extra chrome rendered above the inputs section. */
  header?: ReactNode;
  /** Rendered between the inputs form and the status/results (e.g. mini-graph). */
  slot?: ReactNode;
  /** External error (e.g. a chat run record error) surfaced inline. */
  error?: string | null;
  /**
   * Dense operation-panel layout: smaller fields/buttons, no "Inputs" header,
   * no GenUI attribution footer. Use when embedding as a workflow app surface.
   */
  compact?: boolean;
  /** Show the product logo in the top-right corner (replaces the GenUI footer). */
  brandMark?: boolean;
  className?: string;
}

const EMPTY_OVERLAY: Pick<
  PromptOverlayState,
  'running' | 'blocked' | 'outputs' | 'nodes' | 'assetHistory' | 'assetOrder' | 'errors'
> = {
  running: false,
  blocked: null,
  outputs: null,
  nodes: {},
  assetHistory: [],
  assetOrder: [],
  errors: [],
};

/**
 * GenUI-driven workflow I/O surface: native input form (ingress), live status,
 * pause/review interaction (control plane), generated asset gallery and
 * structured results (egress). Shared by the graph editor's Run panel, the
 * Playground and the in-chat workflow cards.
 */
export function WorkflowOperationPanel({
  flowId,
  inputs,
  outputs,
  overlaySource = 'editor',
  runTarget,
  formId,
  sessionId,
  messageId,
  attachments,
  includeSubmit = true,
  submitLabel,
  inputsHint,
  emptyInputsMessage,
  header,
  slot,
  error,
  compact = false,
  brandMark = false,
  className,
}: WorkflowOperationPanelProps) {
  const { t } = useTranslation();

  const overlay = useExecutionOverlay(
    useShallow((s) => {
      if (overlaySource === 'editor') {
        return {
          promptId: s.promptId,
          running: s.running,
          blocked: s.blocked,
          outputs: s.outputs,
          nodes: s.nodes,
          assetHistory: s.assetHistory,
          assetOrder: s.assetOrder,
          errors: s.errors,
        };
      }
      const o = overlaySource ? s.overlays[overlaySource] : undefined;
      return { promptId: overlaySource ?? null, ...(o ?? EMPTY_OVERLAY) };
    }),
  );

  const { promptId, running, blocked, outputs: resolvedOutputs, nodes, assetHistory, assetOrder, errors: runErrors } =
    overlay;

  const inputSpecs = useMemo(
    () => (inputs ?? []).filter((s): s is WorkflowInputSpec => Boolean(s?.name)),
    [inputs],
  );

  const resolvedFormKey = formId ?? `workflow-inputs-${flowId ?? 'chat'}`;

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

  const headerClass = cn(
    'flex items-center gap-2 px-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground',
    compact ? 'pt-2.5' : 'pt-3',
  );

  return (
    <div className={cn('relative flex min-h-0 flex-col overflow-y-auto', className)}>
      {brandMark ? (
        <AppLogo className="pointer-events-none absolute right-2.5 top-2.5 z-10 size-5 rounded-md opacity-70" />
      ) : null}
      {header}

      {/* Ingress: generated input form */}
      <section className="border-b border-border">
        {compact ? null : (
          <header className={headerClass}>{t('runPanel.inputs', 'Inputs')}</header>
        )}
        {inputSpecs.length > 0 ? (
          <WorkflowInputPanel
            inputs={inputSpecs}
            formKey={resolvedFormKey}
            runTarget={runTarget}
            flowId={flowId ?? ''}
            includeSubmit={includeSubmit}
            submitLabel={submitLabel ?? t('runPanel.run', 'Run')}
            sessionId={sessionId}
            messageId={messageId}
            attachments={attachments}
            compact={compact}
            inputsHint={inputsHint}
            disabled={running}
          />
        ) : (
          <p className="px-4 py-3 text-xs text-muted-foreground">
            {emptyInputsMessage ??
              t(
                'runPanel.noInputs',
                'No workflow inputs declared. Add inputs under Inputs / Outputs, or edit prompt fields directly on nodes.',
              )}
          </p>
        )}
      </section>

      {error ? (
        <div className="mx-3 mt-2.5 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
          <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {error}
        </div>
      ) : null}

      {slot}

      {/* Status */}
      {running ? (
        <div className="flex items-center gap-2 px-4 py-2.5 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary-500" />
          {t('runPanel.running', 'Running...')}
        </div>
      ) : null}

      {/* Control plane: pause / review interaction */}
      {blockedTree ? (
        <section className="border-b border-border">
          <header
            className={cn(
              'flex items-center gap-2 px-4 text-xs font-semibold uppercase tracking-wide text-amber-600 dark:text-amber-400',
              compact ? 'pt-2.5' : 'pt-3',
            )}
          >
            <MessageCircleQuestion className="h-3.5 w-3.5" />
            {t('runPanel.waiting', 'Waiting for your input')}
          </header>
          <GenUiTreeView tree={blockedTree} sessionId={sessionId} messageId={messageId} />
        </section>
      ) : null}

      {/* Egress: generated asset gallery (image / video / 3D) */}
      {assetEntries.length > 0 && !blocked ? (
        <section className="border-b border-border">
          <header className={headerClass}>
            <Images className="h-3.5 w-3.5" />
            {t('runPanel.assets', 'Assets')}
            {assetCount > 0 ? (
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                {assetCount}
              </span>
            ) : null}
          </header>
          {assetEntries.map(({ id, tree }) => (
            <GenUiTreeView key={id} tree={tree} sessionId={sessionId} messageId={messageId} />
          ))}
        </section>
      ) : null}

      {/* Egress: structured results */}
      {outputTree ? (
        <section>
          <header className={headerClass}>
            <SquareActivity className="h-3.5 w-3.5" />
            {t('runPanel.results', 'Results')}
          </header>
          <GenUiTreeView tree={outputTree} sessionId={sessionId} messageId={messageId} />
        </section>
      ) : null}

      {runErrors.length > 0 && !running ? (
        <section className="px-4 py-2.5">
          {runErrors.map((e, i) => (
            <p key={i} className="text-xs text-red-600 dark:text-red-400">
              {e}
            </p>
          ))}
        </section>
      ) : null}
    </div>
  );
}
