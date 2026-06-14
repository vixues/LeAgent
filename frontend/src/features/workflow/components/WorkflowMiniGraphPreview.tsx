import { memo, useRef, useState } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { GitBranch } from 'lucide-react';

import { cn } from '@/lib/utils';
import {
  WorkflowMiniGraphCore,
  type TemplatePreviewUi,
} from './WorkflowMiniGraphCore';

export interface WorkflowMiniGraphPreviewProps {
  flowData?: Record<string, unknown> | null;
  previewUi?: TemplatePreviewUi | null;
  className?: string;
  /** Card thumbnail vs chat inline strip. */
  variant?: 'card' | 'strip';
}

function WorkflowMiniGraphPreviewInner({
  flowData,
  previewUi,
  className,
  variant = 'card',
}: WorkflowMiniGraphPreviewProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [interactive, setInteractive] = useState(variant !== 'card');

  if (import.meta.env.MODE === 'test') {
    return (
      <div
        className={cn(
          'flex items-center justify-center rounded-xl border border-dashed border-border-subtle bg-surface-sunken/40 text-[10px] text-muted-foreground-tertiary',
          variant === 'card' ? 'h-[148px]' : 'h-[300px]',
          className,
        )}
        data-testid="workflow-mini-graph-placeholder"
      >
        Workflow graph
      </div>
    );
  }

  const shellClass = cn(
    'chat-workflow-flow w-full overflow-hidden border border-border-subtle bg-surface-sunken/50 dark:bg-surface-raised/20',
    variant === 'card' ? 'h-[148px] rounded-lg' : 'h-[min(380px,62vh)] min-h-[300px] rounded-2xl',
    className,
  );

  if (variant === 'card' && !interactive) {
    return (
      <div
        ref={rootRef}
        className={cn(shellClass, 'flex flex-col items-center justify-center gap-1 cursor-pointer')}
        onMouseEnter={() => setInteractive(true)}
        onFocus={() => setInteractive(true)}
        tabIndex={0}
        role="button"
        aria-label="Load workflow preview"
      >
        <GitBranch className="h-5 w-5 text-muted-foreground-tertiary" aria-hidden />
        <span className="text-[10px] text-muted-foreground-tertiary">Hover to preview</span>
      </div>
    );
  }

  return (
    <div ref={rootRef} className={shellClass}>
      <ReactFlowProvider>
        <WorkflowMiniGraphCore
          flowData={flowData}
          previewUi={previewUi}
          rootRef={rootRef}
          mode={variant === 'card' ? 'compact' : 'inline'}
          showControls={variant !== 'card'}
          showBackground
        />
      </ReactFlowProvider>
    </div>
  );
}

export const WorkflowMiniGraphPreview = memo(WorkflowMiniGraphPreviewInner);
