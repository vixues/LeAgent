import { memo, useCallback } from 'react';
import {
  Handle,
  Position,
  useReactFlow,
  useStore,
  type NodeProps,
} from '@xyflow/react';

import { cn } from '@/lib/utils';

import { useNodeDefinition } from '../graph/registryContext';
import type { WorkflowNodeData } from '../graph/serialization';
import { useExecutionOverlay } from '../store/executionOverlay';
import { NodeWidget } from './NodeWidget';

const STATUS_RING: Record<string, string> = {
  running: 'ring-2 ring-blue-400 animate-pulse',
  success: 'ring-2 ring-emerald-400',
  error: 'ring-2 ring-red-500',
  blocked: 'ring-2 ring-amber-400',
  cached: 'ring-2 ring-slate-400',
};

function TypedNodeViewImpl({ id, data, selected }: NodeProps) {
  const nodeData = data as WorkflowNodeData;
  const def = useNodeDefinition(nodeData.nodeType);
  const { updateNodeData } = useReactFlow();
  const runState = useExecutionOverlay((s) => s.nodes[id]);

  // Subscribe to incoming edges so connected inputs hide their widget.
  const connectedHandles = useStore(
    useCallback(
      (s) => {
        const set = new Set<string>();
        for (const edge of s.edges) {
          if (edge.target === id && edge.targetHandle) set.add(edge.targetHandle);
        }
        return Array.from(set).sort().join('|');
      },
      [id],
    ),
  );
  const connectedSet = new Set(connectedHandles ? connectedHandles.split('|') : []);

  const setValue = useCallback(
    (slotId: string, value: unknown) => {
      const values = { ...(nodeData.values ?? {}), [slotId]: value };
      updateNodeData(id, { values });
    },
    [id, nodeData.values, updateNodeData],
  );

  const inputs = def?.inputs ?? [];
  const outputs = def?.outputs ?? [];
  const label = nodeData.label || def?.displayName || nodeData.nodeType;
  const ringClass = runState ? STATUS_RING[runState.status] ?? '' : '';

  return (
    <div
      className={cn(
        'min-w-[200px] max-w-[300px] rounded-md border border-border bg-card text-card-foreground shadow-sm',
        selected && 'ring-2 ring-primary',
        ringClass,
      )}
    >
      <div className="flex items-center justify-between gap-2 rounded-t-md border-b border-border bg-muted/60 px-2 py-1">
        <span className="truncate text-xs font-semibold" title={def?.description}>
          {label}
        </span>
        <div className="flex items-center gap-1">
          {def?.experimental && (
            <span className="rounded bg-amber-500/20 px-1 text-[9px] text-amber-600">
              exp
            </span>
          )}
          {def?.deprecated && (
            <span className="rounded bg-red-500/20 px-1 text-[9px] text-red-600">
              deprecated
            </span>
          )}
          {runState?.status && (
            <span className="text-[9px] uppercase text-muted-foreground">
              {runState.status}
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-2 px-2 py-2">
        {inputs.map((slot, index) => {
          const connected = connectedSet.has(slot.id);
          return (
            <div key={`in-${slot.id}`} className="relative">
              <Handle
                id={slot.id}
                type="target"
                position={Position.Left}
                title={`${slot.id}: ${slot.type}`}
                style={{
                  left: -14,
                  top: 8 + index * 2,
                  width: 11,
                  height: 11,
                  background: slot.color,
                  border: '2px solid var(--color-background, #fff)',
                }}
              />
              <div className="flex flex-col gap-0.5">
                <span className="text-[10px] text-muted-foreground">{slot.id}</span>
                {slot.widget && !slot.forceInput ? (
                  <NodeWidget
                    slot={slot}
                    value={nodeData.values?.[slot.id] ?? slot.default}
                    onChange={(v) => setValue(slot.id, v)}
                    connected={connected}
                  />
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      {outputs.length > 0 && (
        <div className="flex flex-col items-end gap-2 border-t border-border px-2 py-2">
          {outputs.map((slot, index) => (
            <div key={`out-${slot.id}`} className="relative w-full text-right">
              <span className="text-[10px] text-muted-foreground">{slot.id}</span>
              <Handle
                id={slot.id}
                type="source"
                position={Position.Right}
                title={`${slot.id}: ${slot.type}`}
                style={{
                  right: -14,
                  top: 8 + index * 2,
                  width: 11,
                  height: 11,
                  background: slot.color,
                  border: '2px solid var(--color-background, #fff)',
                }}
              />
            </div>
          ))}
        </div>
      )}

      {runState?.preview != null && (
        <div className="max-h-24 overflow-auto border-t border-border bg-muted/30 px-2 py-1 text-[10px] text-muted-foreground">
          <PreviewRow preview={runState.preview} />
        </div>
      )}
    </div>
  );
}

function PreviewRow({ preview }: { preview: unknown }) {
  if (typeof preview === 'string') return <span>{preview}</span>;
  if (preview && typeof preview === 'object') {
    const row = preview as Record<string, unknown>;
    if (typeof row.content === 'string') return <span>{row.content}</span>;
    if (typeof row.name === 'string')
      return <span>{`${row.type ?? 'event'}: ${row.name}`}</span>;
    return <span>{JSON.stringify(row).slice(0, 200)}</span>;
  }
  return <span>{String(preview)}</span>;
}

export const TypedNodeView = memo(TypedNodeViewImpl);
