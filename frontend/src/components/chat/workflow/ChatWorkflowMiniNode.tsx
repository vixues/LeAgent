import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { AlertTriangle, Check, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { FlowNode } from '@/stores/flow';
import {
  useExecutionOverlay,
  type NodeRunStatus,
} from '@/features/workflow/store/executionOverlay';
import { useChatWorkflowRunPromptId } from './chatWorkflowRunContext';

const CATEGORY_HANDLE: Record<string, string> = {
  doc: '!bg-orange-500',
  web: '!bg-blue-500',
  data: '!bg-emerald-500',
  llm: '!bg-sky-500',
  email: '!bg-rose-500',
  notification: '!bg-amber-500',
  delay: '!bg-stone-500',
  condition: '!bg-sky-600',
  loop: '!bg-cyan-500',
  webhook: '!bg-pink-500',
  transform: '!bg-teal-500',
  image: '!bg-rose-500',
  trigger: '!bg-amber-500',
  default: '!bg-zinc-500',
};

/** Tinted header strip per category (the title bar). */
const CATEGORY_HEADER: Record<string, string> = {
  doc: 'bg-orange-50/80 dark:bg-orange-950/30',
  web: 'bg-blue-50/80 dark:bg-blue-950/30',
  data: 'bg-emerald-50/80 dark:bg-emerald-950/30',
  llm: 'bg-sky-50/80 dark:bg-sky-950/30',
  email: 'bg-rose-50/80 dark:bg-rose-950/30',
  notification: 'bg-amber-50/80 dark:bg-amber-950/30',
  delay: 'bg-stone-100/80 dark:bg-zinc-900/40',
  condition: 'bg-sky-50/80 dark:bg-sky-950/30',
  loop: 'bg-cyan-50/80 dark:bg-cyan-950/30',
  webhook: 'bg-pink-50/80 dark:bg-pink-950/30',
  transform: 'bg-teal-50/80 dark:bg-teal-950/30',
  image: 'bg-rose-50/80 dark:bg-rose-950/30',
  trigger: 'bg-amber-50/80 dark:bg-amber-950/30',
  default: 'bg-zinc-50/80 dark:bg-zinc-900/40',
};

/** Humanized category caption shown in the card body. */
const CATEGORY_LABEL: Record<string, string> = {
  doc: 'Document',
  web: 'Tool',
  data: 'Data',
  llm: 'LLM',
  email: 'Email',
  notification: 'Notify',
  delay: 'Delay',
  condition: 'Branch',
  loop: 'Loop',
  webhook: 'Webhook',
  transform: 'Transform',
  image: 'Image',
  trigger: 'Flow',
  default: 'Step',
};

/** Header height (px) — anchors are centered on this title bar. */
const HEADER_HEIGHT = 34;

/** Map backend/editor category ids (e.g. workflow/control) to mini-graph palette keys. */
function resolveMiniNodeCategory(raw: string): string {
  const normalized = raw
    .toLowerCase()
    .replace(/&/g, 'and')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  if (normalized in CATEGORY_HANDLE) return normalized;

  const tail = raw.includes('/') ? raw.split('/').pop() ?? raw : raw;
  const tailNorm = tail
    .toLowerCase()
    .replace(/&/g, 'and')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  if (tailNorm in CATEGORY_HANDLE) return tailNorm;

  const aliases: Record<string, string> = {
    workflow_control: 'trigger',
    workflow: 'trigger',
    control: 'trigger',
    start: 'trigger',
    end: 'trigger',
    tool_call: 'web',
    toolcall: 'web',
    llm_call: 'llm',
    llmcall: 'llm',
    parallel: 'loop',
    human_review: 'notification',
    error_handler: 'transform',
    subworkflow: 'transform',
  };
  return aliases[normalized] ?? aliases[tailNorm] ?? 'default';
}

/** Status ring overlaid on the node card while a chat run is in flight. */
const STATUS_RING: Partial<Record<NodeRunStatus, string>> = {
  running: 'ring-2 ring-sky-400/80 dark:ring-sky-400/70',
  success: 'ring-2 ring-emerald-400/80 dark:ring-emerald-400/70',
  error: 'ring-2 ring-rose-400/80 dark:ring-rose-400/70',
  blocked: 'ring-2 ring-amber-400/80 dark:ring-amber-400/70',
};

function useNodeRunStatus(nodeId: string): NodeRunStatus | undefined {
  const promptId = useChatWorkflowRunPromptId();
  return useExecutionOverlay((s) =>
    promptId ? s.overlays[promptId]?.nodes[nodeId]?.status : undefined,
  );
}

function StatusBadge({ status }: { status: NodeRunStatus }) {
  if (status === 'running') {
    return (
      <Loader2
        className="h-3 w-3 shrink-0 animate-spin text-sky-500 dark:text-sky-400"
        aria-hidden
      />
    );
  }
  if (status === 'success' || status === 'cached') {
    return (
      <Check className="h-3 w-3 shrink-0 text-emerald-500 dark:text-emerald-400" aria-hidden />
    );
  }
  if (status === 'error') {
    return (
      <AlertTriangle className="h-3 w-3 shrink-0 text-rose-500 dark:text-rose-400" aria-hidden />
    );
  }
  return null;
}

/** Hidden fallback handle (keeps vertical-layout edges connectable). */
const HIDDEN_HANDLE =
  '!h-1.5 !w-1.5 !min-h-0 !min-w-0 !border-0 !bg-transparent !opacity-0';

function ChatWorkflowMiniNodeInner({ data, id }: NodeProps<FlowNode>) {
  const label = typeof data.label === 'string' && data.label.trim() ? data.label.trim() : 'Node';
  const rawCat = typeof data.category === 'string' ? data.category : 'default';
  const cat = resolveMiniNodeCategory(rawCat);
  const header = CATEGORY_HEADER[cat] ?? CATEGORY_HEADER.default;
  const typeLabel = CATEGORY_LABEL[cat] ?? CATEGORY_LABEL.default;
  const runStatus = useNodeRunStatus(id);
  const ring = runStatus ? STATUS_RING[runStatus] : undefined;

  const anchorFill = CATEGORY_HANDLE[cat] ?? CATEGORY_HANDLE.default;
  const anchorCls = cn(
    '!h-2.5 !w-2.5 !min-h-0 !min-w-0 !rounded-full !border-2 !border-white !shadow-sm',
    'dark:!border-zinc-900',
    anchorFill,
  );
  const anchorStyle = { top: HEADER_HEIGHT / 2 };

  return (
    <div
      className={cn(
        'relative w-[200px] max-w-[220px] rounded-xl border border-border-subtle',
        'bg-surface-elevated shadow-lg transition-shadow text-left',
        ring,
        runStatus === 'pending' ? 'opacity-60' : undefined,
      )}
      data-run-status={runStatus ?? undefined}
    >
      {/* input anchor — sits on the title bar */}
      <Handle type="target" position={Position.Left} className={anchorCls} style={anchorStyle} />
      <Handle type="target" position={Position.Top} className={HIDDEN_HANDLE} />

      {/* title bar */}
      <div
        className={cn(
          'flex items-center gap-2 rounded-t-xl border-b border-border-subtle px-2.5',
          header,
        )}
        style={{ height: HEADER_HEIGHT }}
      >
        <span className="min-w-0 flex-1 truncate text-xs font-semibold leading-none text-foreground">
          {label}
        </span>
        {runStatus ? <StatusBadge status={runStatus} /> : null}
      </div>

      {/* body caption */}
      <div className="rounded-b-xl px-2.5 py-1.5">
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground-tertiary">
          {typeLabel}
        </span>
      </div>

      {/* output anchor — sits on the title bar */}
      <Handle type="source" position={Position.Right} className={anchorCls} style={anchorStyle} />
      <Handle type="source" position={Position.Bottom} className={HIDDEN_HANDLE} />
    </div>
  );
}

export const ChatWorkflowMiniNode = memo(ChatWorkflowMiniNodeInner);
