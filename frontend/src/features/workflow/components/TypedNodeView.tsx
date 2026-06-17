import { memo, useCallback } from 'react';
import {
  Handle,
  Position,
  useReactFlow,
  useStore,
  type NodeProps,
} from '@xyflow/react';

import { cn } from '@/lib/utils';

import { firstMediaItem } from '@/components/canvas/genUi/genUiMedia';

import { useNodeDefinition } from '../graph/registryContext';
import type { InputSlot } from '../graph/objectInfo';
import type { WorkflowNodeData } from '../graph/serialization';
import { typesCompatible } from '../graph/socketTypes';
import { useConnectionDrag } from '../store/connectionDrag';
import { useExecutionOverlay } from '../store/executionOverlay';
import { CameraControlNodeView } from './art/CameraControlNodeView';
import { ShotNodeView, StoryboardNodeView } from './art/StoryboardNodeView';
import { NodeMediaPreview } from './NodeMediaPreview';
import { NodeWidget } from './NodeWidget';
import { ConnectedInputPreview, useUpstreamInputPreview } from './ConnectedInputPreview';

const STATUS_RING: Record<string, string> = {
  running: 'ring-2 ring-blue-400 animate-pulse',
  success: 'ring-2 ring-emerald-400',
  error: 'ring-2 ring-red-500',
  blocked: 'ring-2 ring-amber-400',
  cached: 'ring-2 ring-slate-400',
  skipped: 'ring-2 ring-slate-300 opacity-70',
};

function TypedNodeViewImpl(props: NodeProps) {
  const nodeData = props.data as WorkflowNodeData;
  switch (nodeData.nodeType) {
    case 'Art.CameraControl':
      return <CameraControlNodeView {...props} />;
    case 'Art.Storyboard':
      return <StoryboardNodeView {...props} />;
    case 'Art.Shot':
      return <ShotNodeView {...props} />;
    default:
      return <StandardTypedNodeView {...props} />;
  }
}

function StandardTypedNodeView({ id, data, selected }: NodeProps) {
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
  const mediaItem = runState?.ui ? firstMediaItem(runState.ui) : null;
  const label = nodeData.label || def?.displayName || nodeData.nodeType;
  const ringClass = runState ? STATUS_RING[runState.status] ?? '' : '';
  const missing = !def;
  const mode = nodeData.mode;

  // ComfyUI-style title accent: tint the header with the node's primary
  // socket color so nodes read as colour-coded at a glance.
  const accent =
    outputs.find((s) => s.color)?.color ??
    inputs.find((s) => s.color)?.color ??
    (missing ? '#f87171' : 'rgb(var(--color-primary))');

  // Dim nodes with no compatible slot during a link drag (ComfyUI affordance).
  const dragType = useConnectionDrag((s) => s.type);
  const dragDirection = useConnectionDrag((s) => s.direction);
  const dimmed =
    dragType != null &&
    !(dragDirection === 'out'
      ? inputs.some((slot) => typesCompatible(dragType, slot.type))
      : outputs.some((slot) => typesCompatible(slot.type, dragType)));

  return (
    <div
      className={cn(
        'relative min-w-[200px] max-w-[300px] overflow-visible rounded-lg border border-border bg-surface-elevated text-foreground shadow-md',
        selected && 'ring-2 ring-primary',
        ringClass,
        // ComfyUI parity: muted nodes dim out, bypassed nodes tint purple.
        mode === 'mute' && 'opacity-40 saturate-50',
        mode === 'bypass' &&
          'border-violet-400 bg-violet-50/80 dark:border-violet-600 dark:bg-violet-950/50',
        missing && 'border-dashed border-red-400 dark:border-red-600',
        dimmed && 'opacity-30 transition-opacity',
      )}
    >
      {/* Colour-coded title bar (ComfyUI node colour). */}
      <div
        className="flex items-center justify-between gap-2 border-b border-border px-2 py-1.5"
        style={{ backgroundColor: `color-mix(in srgb, ${accent} 22%, rgb(var(--color-surface-sunken)))` }}
      >
        <span className="truncate text-xs font-semibold" title={def?.description}>
          {label}
        </span>
        <div className="flex items-center gap-1">
          {mode && (
            <span
              className={cn(
                'rounded px-1 text-[9px] uppercase',
                mode === 'mute'
                  ? 'bg-slate-500/20 text-slate-500'
                  : 'bg-violet-500/20 text-violet-600 dark:text-violet-400',
              )}
            >
              {mode}
            </span>
          )}
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

      {missing && (
        <div className="relative px-2 py-2 text-[10px] leading-relaxed text-red-600 dark:text-red-400">
          {/* Generic handles keep stored links visible for missing types. */}
          <Handle
            id="__missing_in"
            type="target"
            position={Position.Left}
            style={{ left: -14, width: 11, height: 11, background: '#f87171' }}
          />
          <Handle
            id="__missing_out"
            type="source"
            position={Position.Right}
            style={{ right: -14, width: 11, height: 11, background: '#f87171' }}
          />
          Unknown node type <code className="font-mono">{nodeData.nodeType}</code>.
          The stored configuration is preserved; install or re-enable the node
          pack to run this workflow.
        </div>
      )}

      {runState?.progress != null && runState.status === 'running' && (
        <div className="h-0.5 w-full bg-surface-sunken">
          <div
            className="h-full bg-blue-400 transition-[width]"
            style={{ width: `${Math.round(runState.progress * 100)}%` }}
          />
        </div>
      )}

      <div className="flex flex-col gap-2 px-2 py-2">
        {inputs.map((slot, index) => (
          <InputSlotRow
            key={`in-${slot.id}`}
            nodeId={id}
            slot={slot}
            index={index}
            connected={connectedSet.has(slot.id)}
            value={nodeData.values?.[slot.id] ?? slot.default}
            onChange={(v) => setValue(slot.id, v)}
          />
        ))}
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

      {mediaItem && (
        <div className="border-t border-border bg-surface-sunken/50 px-2 py-2">
          <NodeMediaPreview item={mediaItem} />
        </div>
      )}

      {runState?.preview != null && (
        <div className="max-h-24 overflow-auto border-t border-border bg-surface-sunken px-2 py-1 text-[10px] text-muted-foreground">
          <PreviewRow preview={runState.preview} />
        </div>
      )}
    </div>
  );
}

function InputSlotRow({
  nodeId,
  slot,
  index,
  connected,
  value,
  onChange,
}: {
  nodeId: string;
  slot: InputSlot;
  index: number;
  connected: boolean;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const upstreamPreview = useUpstreamInputPreview(nodeId, slot.id);

  return (
    <div className="relative">
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
        {connected && upstreamPreview ? (
          <ConnectedInputPreview descriptor={upstreamPreview} />
        ) : slot.widget && !slot.forceInput ? (
          <NodeWidget slot={slot} value={value} onChange={onChange} connected={connected} />
        ) : connected ? (
          <div className="text-[10px] italic text-muted-foreground">{slot.id} ← linked</div>
        ) : null}
      </div>
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
