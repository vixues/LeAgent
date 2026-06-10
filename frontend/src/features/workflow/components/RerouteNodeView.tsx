/**
 * ComfyUI-style reroute dot: a UI-only waypoint that relays a single link so
 * long wires can be routed cleanly. Flattened out of the executable graph on
 * serialize (see `graph/serialization.ts`).
 */
import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';

import { cn } from '@/lib/utils';

function RerouteNodeViewInner({ selected }: NodeProps) {
  return (
    <div
      className={cn(
        'h-4 w-4 rounded-full border-2 bg-surface transition-colors',
        selected
          ? 'border-primary-500 shadow-glow'
          : 'border-gray-400 dark:border-gray-500 hover:border-primary-400',
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        id="in"
        className="!h-2.5 !w-2.5 !-left-1 !border-0 !bg-transparent"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="out"
        className="!h-2.5 !w-2.5 !-right-1 !border-0 !bg-transparent"
      />
    </div>
  );
}

export const RerouteNodeView = memo(RerouteNodeViewInner);
