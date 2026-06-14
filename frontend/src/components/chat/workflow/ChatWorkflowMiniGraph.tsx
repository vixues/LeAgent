import {
  memo,
  useEffect,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Maximize2 } from 'lucide-react';
import { ReactFlowProvider } from '@xyflow/react';

import { Button } from '@/components/ui/Button';
import { Modal, ModalHeader } from '@/components/ui/Modal';
import { cn } from '@/lib/utils';
import { WorkflowMiniGraphCore } from '@/features/workflow/components/WorkflowMiniGraphCore';
import './chat-workflow-flow.css';

export interface ChatWorkflowMiniGraphProps {
  flowData: Record<string, unknown>;
  /** Shown in the floating preview modal header (e.g. workflow title). */
  previewTitle?: string;
}

function ChatWorkflowMiniGraphInner({ flowData, previewTitle }: ChatWorkflowMiniGraphProps) {
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
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-end px-0.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="shrink-0 gap-1.5"
            leftIcon={<Maximize2 className="h-3.5 w-3.5" aria-hidden />}
            aria-label={t('chat.workflow.expandFloatingPreview')}
            title={t('chat.workflow.expandFloatingHint')}
            onClick={() => setFloatingOpen(true)}
          >
            {t('chat.workflow.expandFloatingPreview')}
          </Button>
        </div>
        <div
          ref={rootRef}
          className="chat-workflow-flow h-[min(380px,62vh)] min-h-[300px] w-full overflow-hidden rounded-2xl border border-border-subtle bg-surface-sunken/50 dark:bg-surface-raised/20"
        >
          <ReactFlowProvider>
            <WorkflowMiniGraphCore mode="inline" flowData={flowData} rootRef={rootRef} />
          </ReactFlowProvider>
        </div>
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
              <WorkflowMiniGraphCore mode="overlay" flowData={flowData} rootRef={overlayRootRef} />
            </ReactFlowProvider>
          </div>
        </div>
      </Modal>
    </>
  );
}

export const ChatWorkflowMiniGraph = memo(ChatWorkflowMiniGraphInner);
