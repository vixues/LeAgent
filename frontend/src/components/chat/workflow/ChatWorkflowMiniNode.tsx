import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { cn } from '@/lib/utils';
import type { FlowNode } from '@/stores/flow';

/** Category tint — visible on light/dark, aligned with Flow editor semantics. */
const CATEGORY_CARD: Record<string, string> = {
  doc: 'border-orange-200/90 bg-orange-50/95 text-orange-950 dark:border-orange-800/70 dark:bg-orange-950/40 dark:text-orange-50',
  web: 'border-blue-200/90 bg-blue-50/95 text-blue-950 dark:border-blue-800/70 dark:bg-blue-950/40 dark:text-blue-50',
  data: 'border-emerald-200/90 bg-emerald-50/95 text-emerald-950 dark:border-emerald-800/70 dark:bg-emerald-950/40 dark:text-emerald-50',
  llm: 'border-sky-200/90 bg-sky-50/95 text-sky-950 dark:border-sky-800/70 dark:bg-sky-950/40 dark:text-sky-50',
  email: 'border-rose-200/90 bg-rose-50/95 text-rose-950 dark:border-rose-800/70 dark:bg-rose-950/40 dark:text-rose-50',
  notification:
    'border-amber-200/90 bg-amber-50/95 text-amber-950 dark:border-amber-800/70 dark:bg-amber-950/40 dark:text-amber-50',
  delay: 'border-stone-300/90 bg-stone-100/95 text-stone-900 dark:border-zinc-600/80 dark:bg-zinc-900/50 dark:text-zinc-100',
  condition:
    'border-sky-300/90 bg-sky-50/95 text-sky-950 dark:border-sky-700/70 dark:bg-sky-950/40 dark:text-sky-50',
  loop: 'border-cyan-200/90 bg-cyan-50/95 text-cyan-950 dark:border-cyan-800/70 dark:bg-cyan-950/40 dark:text-cyan-50',
  webhook: 'border-pink-200/90 bg-pink-50/95 text-pink-950 dark:border-pink-800/70 dark:bg-pink-950/40 dark:text-pink-50',
  transform:
    'border-teal-200/90 bg-teal-50/95 text-teal-950 dark:border-teal-800/70 dark:bg-teal-950/40 dark:text-teal-50',
  image: 'border-rose-200/90 bg-rose-50/95 text-rose-950 dark:border-rose-800/70 dark:bg-rose-950/40 dark:text-rose-50',
  trigger:
    'border-amber-300/90 bg-amber-50/95 text-amber-950 dark:border-amber-800/70 dark:bg-amber-950/45 dark:text-amber-50',
  default:
    'border-zinc-200/90 bg-zinc-50/95 text-zinc-900 dark:border-zinc-600/80 dark:bg-zinc-900/45 dark:text-zinc-100',
};

const CATEGORY_DOT: Record<string, string> = {
  doc: 'bg-orange-500',
  web: 'bg-blue-500',
  data: 'bg-emerald-500',
  llm: 'bg-sky-500',
  email: 'bg-rose-500',
  notification: 'bg-amber-500',
  delay: 'bg-stone-500',
  condition: 'bg-sky-600',
  loop: 'bg-cyan-500',
  webhook: 'bg-pink-500',
  transform: 'bg-teal-500',
  image: 'bg-rose-500',
  trigger: 'bg-amber-500',
  default: 'bg-zinc-500',
};

function ChatWorkflowMiniNodeInner({ data }: NodeProps<FlowNode>) {
  const label = typeof data.label === 'string' && data.label.trim() ? data.label.trim() : 'Node';
  const rawCat = typeof data.category === 'string' ? data.category : 'default';
  const cat = rawCat in CATEGORY_CARD ? rawCat : 'default';
  const card = CATEGORY_CARD[cat] ?? CATEGORY_CARD.default;
  const dot = CATEGORY_DOT[cat] ?? CATEGORY_DOT.default;

  return (
    <div
      className={cn(
        'relative min-w-[120px] max-w-[220px] rounded-2xl border-2 px-3 py-2.5 shadow-soft',
        'text-left',
        card,
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !min-h-0 !min-w-0 !border-0 !bg-transparent !opacity-0"
      />
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2 !w-2 !min-h-0 !min-w-0 !border-0 !bg-transparent !opacity-0"
      />
      <div className="flex items-start gap-2">
        <span className={cn('mt-1.5 h-2 w-2 shrink-0 rounded-full ring-2 ring-white/50 dark:ring-black/20', dot)} aria-hidden />
        <span className="text-xs font-medium leading-snug line-clamp-4">{label}</span>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !min-h-0 !min-w-0 !border-0 !bg-transparent !opacity-0"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2 !w-2 !min-h-0 !min-w-0 !border-0 !bg-transparent !opacity-0"
      />
    </div>
  );
}

export const ChatWorkflowMiniNode = memo(ChatWorkflowMiniNodeInner);
