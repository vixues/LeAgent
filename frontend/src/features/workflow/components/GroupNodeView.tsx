/**
 * Group frame: a UI-only container (ComfyUI "group") used to visually bundle
 * nodes. Children are parented via React Flow's `parentId` and move with the
 * frame. Never serialized into the executable graph.
 */
import { memo } from 'react';
import { NodeResizer, type NodeProps, type Node } from '@xyflow/react';

import { cn } from '@/lib/utils';

export interface GroupNodeData extends Record<string, unknown> {
  label?: string;
}

function GroupNodeViewInner({ data, selected }: NodeProps<Node<GroupNodeData>>) {
  return (
    <>
      <NodeResizer
        isVisible={selected}
        minWidth={160}
        minHeight={120}
        lineClassName="!border-primary-400"
        handleClassName="!h-2.5 !w-2.5 !rounded-sm !border-primary-400 !bg-surface"
      />
      <div
        className={cn(
          'h-full w-full rounded-xl border-2 border-dashed',
          'bg-primary-500/[0.04] dark:bg-primary-400/[0.06]',
          selected
            ? 'border-primary-400'
            : 'border-gray-300 dark:border-gray-600',
        )}
      >
        <div className="px-3 py-1.5 text-xs font-semibold text-muted-foreground select-none">
          {(data.label as string) || 'Group'}
        </div>
      </div>
    </>
  );
}

export const GroupNodeView = memo(GroupNodeViewInner);
