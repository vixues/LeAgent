import { memo, useCallback, useMemo } from 'react';
import {
  Handle,
  Position,
  useReactFlow,
  useStore,
  type NodeProps,
} from '@xyflow/react';
import { Copy, GripVertical, Plus, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useNodeDefinition } from '../../graph/registryContext';
import type { WorkflowNodeData } from '../../graph/serialization';
import { DEFAULT_SOCKET_COLORS } from '../../graph/socketTypes';
import { useExecutionOverlay } from '../../store/executionOverlay';
import { useInboundEdges } from '../../hooks/useInboundEdges';
import { NodeMediaPreview } from '../NodeMediaPreview';
import { NodeShell } from './NodeShell';

interface ShotRow {
  sourceId: string;
  name: string;
  prompt: string;
  duration: number;
  fps: number;
}

function ShotNodeViewImpl({ id, data, selected }: NodeProps) {
  const nodeData = data as WorkflowNodeData;
  const def = useNodeDefinition('Art.Shot');
  const { updateNodeData } = useReactFlow();
  const { t } = useTranslation('workflows');
  const runState = useExecutionOverlay((s) => s.nodes[id]);
  const values = nodeData.values ?? {};
  const name = String(values.name ?? '').trim() || t('storyboard.shotDefault', { defaultValue: 'Shot' });
  const duration = Number(values.duration ?? 3);
  const accent = DEFAULT_SOCKET_COLORS.OBJECT;

  const setValue = useCallback(
    (key: string, value: unknown) => {
      updateNodeData(id, { values: { ...values, [key]: value } });
    },
    [id, updateNodeData, values],
  );

  return (
    <NodeShell
      title={nodeData.label || name}
      accent={accent}
      selected={selected}
      status={runState?.status}
      mode={nodeData.mode}
      width={260}
    >
      <div className="space-y-1.5 p-2">
        {def?.inputs
          .filter((s) => s.id !== 'prompt' && s.id !== 'name')
          .map((slot, index) => (
          <div key={slot.id} className="relative">
            <Handle
              id={slot.id}
              type="target"
              position={Position.Left}
              style={{
                left: -14,
                top: 8 + index * 4,
                width: 11,
                height: 11,
                background: slot.color,
                border: '2px solid var(--color-background, #fff)',
              }}
            />
            <span className="text-[9px] text-muted-foreground">{slot.id}</span>
          </div>
        ))}
        <input
          type="text"
          className="nodrag w-full rounded border border-border bg-background px-1.5 py-0.5 text-[10px]"
          placeholder={t('storyboard.shotDefault', { defaultValue: 'Shot name' })}
          value={String(values.name ?? '')}
          onChange={(e) => setValue('name', e.target.value)}
        />
        <textarea
          className="nodrag min-h-[52px] w-full resize-y rounded border border-border bg-background px-1.5 py-1 text-[10px] leading-snug"
          placeholder={t('storyboard.emptyPrompt', { defaultValue: 'Shot prompt…' })}
          value={String(values.prompt ?? '')}
          onChange={(e) => setValue('prompt', e.target.value)}
        />
        <div className="flex gap-2">
          <label className="flex flex-1 flex-col gap-0.5 text-[9px] text-muted-foreground">
            {t('storyboard.duration', { defaultValue: 'Duration' })}
            <input
              type="number"
              className="nodrag rounded border border-border bg-background px-1 py-0.5 text-[10px]"
              min={1}
              max={20}
              value={duration}
              onChange={(e) => setValue('duration', Number(e.target.value))}
            />
          </label>
          <label className="flex flex-1 flex-col gap-0.5 text-[9px] text-muted-foreground">
            FPS
            <input
              type="number"
              className="nodrag rounded border border-border bg-background px-1 py-0.5 text-[10px]"
              min={8}
              max={60}
              value={Number(values.fps ?? 24)}
              onChange={(e) => setValue('fps', Number(e.target.value))}
            />
          </label>
        </div>
      </div>
      <div className="relative border-t border-border px-2 py-1.5 text-right">
        <span className="text-[10px] text-muted-foreground">shot</span>
        <Handle
          id="shot"
          type="source"
          position={Position.Right}
          style={{
            right: -14,
            top: 10,
            width: 11,
            height: 11,
            background: DEFAULT_SOCKET_COLORS.OBJECT,
            border: '2px solid var(--color-background, #fff)',
          }}
        />
      </div>
    </NodeShell>
  );
}

function StoryboardNodeViewImpl({ id, data, selected }: NodeProps) {
  const nodeData = data as WorkflowNodeData;
  const def = useNodeDefinition('Art.Storyboard');
  const { t } = useTranslation('workflows');
  const { updateNodeData, setNodes, setEdges, getNode } = useReactFlow();
  const runState = useExecutionOverlay((s) => s.nodes[id]);
  const shotEdges = useInboundEdges(id, 'shots');
  const allNodes = useStore((s) => s.nodes);

  const values = nodeData.values ?? {};
  const shotOrder = (values.shot_order as string[] | undefined) ?? [];
  const batchDuration = Number(values.batch_duration ?? 3);
  const batchFps = Number(values.batch_fps ?? 24);

  const shots: ShotRow[] = useMemo(() => {
    const byId = new Map<string, ShotRow>();
    for (const edge of shotEdges) {
      const src = allNodes.find((n) => n.id === edge.source);
      if (!src) continue;
      const wf = src.data as WorkflowNodeData;
      const v = wf.values ?? {};
      byId.set(edge.source, {
        sourceId: edge.source,
        name: String(v.name ?? wf.label ?? edge.source.slice(0, 6)),
        prompt: String(v.prompt ?? '').slice(0, 80),
        duration: Number(v.duration ?? 3),
        fps: Number(v.fps ?? 24),
      });
    }
    const ordered: ShotRow[] = [];
    for (const sid of shotOrder) {
      const row = byId.get(sid);
      if (row) {
        ordered.push(row);
        byId.delete(sid);
      }
    }
    for (const row of byId.values()) ordered.push(row);
    return ordered;
  }, [allNodes, shotEdges, shotOrder]);

  const totalDuration = shots.reduce((s, r) => s + r.duration, 0) || 1;

  const setValues = useCallback(
    (patch: Record<string, unknown>) => {
      updateNodeData(id, { values: { ...values, ...patch } });
    },
    [id, updateNodeData, values],
  );

  const reorder = useCallback(
    (from: number, to: number) => {
      if (from === to || from < 0 || to < 0 || from >= shots.length || to >= shots.length) return;
      const order = shots.map((s) => s.sourceId);
      const [item] = order.splice(from, 1);
      if (!item) return;
      order.splice(to, 0, item);
      setValues({ shot_order: order });
    },
    [shots, setValues],
  );

  const insertShot = useCallback(() => {
    const self = getNode(id);
    if (!self) return;
    const newId = `shot-${Date.now().toString(36)}`;
    const y = self.position.y + shots.length * 72;
    setNodes((nds) => [
      ...nds,
      {
        id: newId,
        type: 'workflow',
        position: { x: self.position.x - 300, y },
        data: {
          nodeType: 'Art.Shot',
          label: t('storyboard.newShot', { defaultValue: 'New shot' }),
          category: 'art/storyboard',
          values: { prompt: '', duration: batchDuration, fps: batchFps },
        } satisfies WorkflowNodeData,
      },
    ]);
    setEdges((eds) => [
      ...eds,
      {
        id: `e-${newId}-${id}-shots`,
        source: newId,
        target: id,
        sourceHandle: 'shot',
        targetHandle: 'shots',
        type: 'workflow',
        data: { color: DEFAULT_SOCKET_COLORS.ARRAY },
      },
    ]);
    setValues({ shot_order: [...shots.map((s) => s.sourceId), newId] });
  }, [batchDuration, batchFps, getNode, id, setEdges, setNodes, setValues, shots, t]);

  const duplicateShot = useCallback(
    (sourceId: string) => {
      const src = allNodes.find((n) => n.id === sourceId);
      if (!src) return;
      const self = getNode(id);
      if (!self) return;
      const newId = `shot-${Date.now().toString(36)}`;
      const wf = src.data as WorkflowNodeData;
      setNodes((nds) => [
        ...nds,
        {
          id: newId,
          type: 'workflow',
          position: { x: src.position.x, y: src.position.y + 80 },
          data: {
            ...wf,
            values: { ...(wf.values ?? {}) },
          },
        },
      ]);
      setEdges((eds) => [
        ...eds,
        {
          id: `e-${newId}-${id}-shots`,
          source: newId,
          target: id,
          sourceHandle: 'shot',
          targetHandle: 'shots',
          type: 'workflow',
          data: { color: DEFAULT_SOCKET_COLORS.ARRAY },
        },
      ]);
      const idx = shots.findIndex((s) => s.sourceId === sourceId);
      const order = shots.map((s) => s.sourceId);
      order.splice(idx + 1, 0, newId);
      setValues({ shot_order: order });
    },
    [allNodes, getNode, id, setEdges, setNodes, setValues, shots],
  );

  const removeFromBoard = useCallback(
    (sourceId: string) => {
      setEdges((eds) => eds.filter((e) => !(e.source === sourceId && e.target === id)));
      setValues({ shot_order: shots.map((s) => s.sourceId).filter((s) => s !== sourceId) });
    },
    [id, setEdges, setValues, shots],
  );

  const applyBatch = useCallback(() => {
    setNodes((nds) =>
      nds.map((n) => {
        if (!shots.some((s) => s.sourceId === n.id)) return n;
        const wf = n.data as WorkflowNodeData;
        return {
          ...n,
          data: {
            ...wf,
            values: { ...(wf.values ?? {}), duration: batchDuration, fps: batchFps },
          },
        };
      }),
    );
  }, [batchDuration, batchFps, setNodes, shots]);

  const genUiVideos = useMemo(() => {
    const ui = runState?.ui;
    if (!ui?.root?.children) return [];
    const items: { src: string; caption?: string }[] = [];
    for (const child of ui.root.children) {
      if (child.kind === 'Video' && typeof child.props?.src === 'string') {
        items.push({ src: child.props.src, caption: String(child.props.caption ?? '') });
      }
    }
    return items;
  }, [runState?.ui]);

  const accent = DEFAULT_SOCKET_COLORS.ARRAY;

  return (
    <NodeShell
      title={nodeData.label || def?.displayName || 'Storyboard'}
      accent={accent}
      selected={selected}
      status={runState?.status}
      mode={nodeData.mode}
      width={380}
    >
      <div className="flex flex-col gap-2 p-2">
        <div className="relative">
          <Handle
            id="shots"
            type="target"
            position={Position.Left}
            title="shots: ARRAY"
            style={{
              left: -14,
              top: 40,
              width: 11,
              height: 11,
              background: accent,
              border: '2px solid var(--color-background, #fff)',
            }}
          />
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] font-medium text-foreground">
              {t('storyboard.shotList', { defaultValue: 'Shots' })} ({shots.length})
            </span>
            <button
              type="button"
              className="nodrag inline-flex items-center gap-0.5 rounded border border-border bg-background px-1.5 py-0.5 text-[10px] hover:bg-muted"
              onClick={insertShot}
            >
              <Plus className="h-3 w-3" />
              {t('storyboard.insert', { defaultValue: 'Insert' })}
            </button>
          </div>

          <ul className="mt-1 max-h-36 space-y-1 overflow-auto">
            {shots.length === 0 ? (
              <li className="rounded border border-dashed border-border px-2 py-3 text-center text-[10px] text-muted-foreground">
                {t('storyboard.connectShots', { defaultValue: 'Connect Art.Shot nodes to shots' })}
              </li>
            ) : (
              shots.map((shot, index) => (
                <li
                  key={shot.sourceId}
                  className="group flex items-start gap-1 rounded border border-border/70 bg-background/60 px-1 py-1"
                  draggable
                  onDragStart={(e) => e.dataTransfer.setData('text/plain', String(index))}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const from = Number(e.dataTransfer.getData('text/plain'));
                    reorder(from, index);
                  }}
                >
                  <GripVertical className="mt-0.5 h-3.5 w-3.5 shrink-0 cursor-grab text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-1">
                      <span className="truncate text-[10px] font-medium">{shot.name}</span>
                      <span className="shrink-0 text-[9px] text-muted-foreground">{shot.duration}s</span>
                    </div>
                    <p className="line-clamp-1 text-[9px] text-muted-foreground">{shot.prompt || '—'}</p>
                  </div>
                  <div className="flex shrink-0 flex-col gap-0.5 opacity-0 transition group-hover:opacity-100">
                    <button
                      type="button"
                      className="nodrag rounded p-0.5 hover:bg-muted"
                      title={t('storyboard.duplicate', { defaultValue: 'Duplicate' })}
                      onClick={() => duplicateShot(shot.sourceId)}
                    >
                      <Copy className="h-3 w-3" />
                    </button>
                    <button
                      type="button"
                      className="nodrag rounded p-0.5 hover:bg-muted"
                      title={t('storyboard.remove', { defaultValue: 'Remove link' })}
                      onClick={() => removeFromBoard(shot.sourceId)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                </li>
              ))
            )}
          </ul>
        </div>

        <div>
          <span className="text-[9px] uppercase text-muted-foreground">
            {t('storyboard.timeline', { defaultValue: 'Timeline' })} · {totalDuration}s
          </span>
          <div className="mt-1 flex h-5 overflow-hidden rounded border border-border/60">
            {shots.map((shot) => (
              <div
                key={shot.sourceId}
                className="h-full border-r border-border/40 bg-primary/30 last:border-r-0"
                style={{ width: `${(shot.duration / totalDuration) * 100}%` }}
                title={`${shot.name} (${shot.duration}s)`}
              />
            ))}
          </div>
        </div>

        <div className="rounded border border-border/60 bg-surface-sunken p-1.5">
          <span className="text-[9px] uppercase text-muted-foreground">
            {t('storyboard.batch', { defaultValue: 'Batch settings' })}
          </span>
          <div className="mt-1 flex items-end gap-2">
            <label className="flex flex-1 flex-col gap-0.5 text-[9px]">
              {t('storyboard.duration', { defaultValue: 'Duration (s)' })}
              <input
                type="number"
                className="nodrag rounded border border-border bg-background px-1 py-0.5 text-[10px]"
                min={1}
                max={20}
                value={batchDuration}
                onChange={(e) => setValues({ batch_duration: Number(e.target.value) })}
              />
            </label>
            <label className="flex flex-1 flex-col gap-0.5 text-[9px]">
              FPS
              <input
                type="number"
                className="nodrag rounded border border-border bg-background px-1 py-0.5 text-[10px]"
                min={8}
                max={60}
                value={batchFps}
                onChange={(e) => setValues({ batch_fps: Number(e.target.value) })}
              />
            </label>
            <button
              type="button"
              className="nodrag rounded bg-primary px-2 py-1 text-[10px] text-primary-foreground hover:opacity-90"
              onClick={applyBatch}
            >
              {t('storyboard.applyAll', { defaultValue: 'Apply' })}
            </button>
          </div>
        </div>

        {(genUiVideos.length > 0) && (
          <div className="rounded border border-border/60 bg-background/40 p-1.5">
            <span className="text-[9px] uppercase text-muted-foreground">
              {t('storyboard.outputSummary', { defaultValue: 'Shot outputs' })}
            </span>
            <div className="mt-1 grid grid-cols-2 gap-1">
              {genUiVideos.map((item, i) => (
                <div key={i} className="overflow-hidden rounded border border-border/50">
                  <NodeMediaPreview item={{ kind: 'Video', src: item.src, caption: item.caption }} />
                  <span className="block truncate px-1 py-0.5 text-[9px] text-muted-foreground">
                    {item.caption || `Shot ${i + 1}`}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="relative border-t border-border px-2 py-2">
        {def?.outputs.map((slot, index) => (
          <div key={slot.id} className="relative text-right text-[10px] text-muted-foreground">
            {slot.id}
            <Handle
              id={slot.id}
              type="source"
              position={Position.Right}
              style={{
                right: -14,
                top: 8 + index * 18,
                width: 11,
                height: 11,
                background: slot.color,
                border: '2px solid var(--color-background, #fff)',
              }}
            />
          </div>
        ))}
      </div>
    </NodeShell>
  );
}

export const ShotNodeView = memo(ShotNodeViewImpl);
export const StoryboardNodeView = memo(StoryboardNodeViewImpl);
