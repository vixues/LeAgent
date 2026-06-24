import {
  memo,
  useEffect,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Maximize2 } from 'lucide-react';
import { ReactFlowProvider, ControlButton } from '@xyflow/react';

import { Modal, ModalHeader } from '@/components/ui/Modal';
import { cn } from '@/lib/utils';
import { WorkflowMiniGraphCore } from '@/features/workflow/components/WorkflowMiniGraphCore';
import './chat-workflow-flow.css';

export interface ChatWorkflowMiniGraphProps {
  flowData: Record<string, unknown>;
  /** Shown in the floating preview modal header (e.g. workflow title). */
  previewTitle?: string;
  /** Active execution prompt id; enables live per-node status overlay. */
  runPromptId?: string | null;
  /** Workflow content digest shown in the graph pane corner. */
  digest?: string | null;
}

function ChatWorkflowMiniGraphInner({
  flowData,
  previewTitle,
  runPromptId = null,
  digest = null,
}: ChatWorkflowMiniGraphProps) {
  const { t } = useTranslation();
  const [floatingOpen, setFloatingOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const overlayRootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!floatingOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFloatingOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [floatingOpen]);

  const modalTitle =
    typeof previewTitle === 'string' && previewTitle.trim()
      ? previewTitle.trim()
      : t('chat.workflow.embedFallbackTitle');

  if (import.meta.env.MODE === 'test') {
    return (
      <div
        className="flex h-[300px] min-h-[300px] items-center justify-center rounded-2xl border border-dashed border-border-subtle bg-surface-raised/50 text-xs text-muted-foreground-tertiary"
        data-testid="chat-workflow-mini-graph-placeholder"
      >
        Workflow graph
      </div>
    );
  }

  return (
    <>
      <div
        ref={rootRef}
        className="chat-workflow-flow h-[min(380px,62vh)] min-h-[300px] w-full overflow-hidden rounded-2xl border border-border-subtle bg-surface-sunken/50 dark:bg-surface-raised/20"
      >
        <ReactFlowProvider>
          <WorkflowMiniGraphCore
            mode="inline"
            flowData={flowData}
            rootRef={rootRef}
            runPromptId={runPromptId}
            digest={digest}
            extraControlButtons={
              <ControlButton
                onClick={() => setFloatingOpen(true)}
                title={t('chat.workflow.expandFloatingHint')}
                aria-label={t('chat.workflow.expandFloatingPreview')}
              >
                <Maximize2 className="h-4 w-4" aria-hidden />
              </ControlButton>
            }
          />
        </ReactFlowProvider>
      </div>

      <Modal
        isOpen={floatingOpen}
        onClose={() => setFloatingOpen(false)}
        fullViewport
        size="2xl"
        className={cn(
          '!max-h-[92vh] !max-w-[min(96vw,1440px)] w-full !overflow-hidden',
          'flex min-h-0 flex-col p-0',
        )}
      >
        <ModalHeader onClose={() => setFloatingOpen(false)}>{modalTitle}</ModalHeader>
        <div className="px-3 pb-3 pt-1">
          <p className="pb-2 text-[11px] leading-snug text-muted-foreground-tertiary">
            {t('chat.workflow.expandFloatingHint')}
          </p>
          <div
            ref={overlayRootRef}
            className="chat-workflow-flow h-[min(76vh,calc(100dvh-10rem))] min-h-[400px] w-full overflow-hidden rounded-xl border border-border-subtle bg-surface-sunken/40 dark:bg-surface-raised/25"
          >
            <ReactFlowProvider>
              <WorkflowMiniGraphCore
                mode="overlay"
                flowData={flowData}
                rootRef={overlayRootRef}
                runPromptId={runPromptId}
              />
            </ReactFlowProvider>
          </div>
        </div>
      </Modal>
    </>
  );
}

export const ChatWorkflowMiniGraph = memo(ChatWorkflowMiniGraphInner);
