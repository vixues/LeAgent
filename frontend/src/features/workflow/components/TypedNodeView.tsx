import { memo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Handle,
  Position,
  useReactFlow,
  useStore,
  type NodeProps,
} from '@xyflow/react';

import { cn } from '@/lib/utils';

import {
  mediaFromNodeRunState,
  type GenUiMediaItem,
} from '@/components/canvas/genUi/genUiMedia';
import { extractApiFilePreviewId } from '@/components/chat/media/chatMediaUtils';

import { useNodeDefinition } from '../graph/registryContext';
import type { InputSlot } from '../graph/objectInfo';
import type { WorkflowNodeData } from '../graph/serialization';
import { typesCompatible } from '../graph/socketTypes';
import { useConnectionDrag } from '../store/connectionDrag';
import { useExecutionOverlay, assetVersionCount } from '../store/executionOverlay';
import { CameraControlNodeView } from './art/CameraControlNodeView';
import { ShotNodeView, StoryboardNodeView } from './art/StoryboardNodeView';
import { NodeArtifactPreview, type ArtifactDescriptor, type ArtifactKind } from './NodeArtifactPreview';
import { NodeWidget } from './NodeWidget';
import { ConnectedInputPreview, useUpstreamInputPreview } from './ConnectedInputPreview';
import { ART_IMAGE_NODE_TYPES, ArtModelSelect, ArtPresetSelect } from './ArtGenWidgets';
import { AgentModelSelect, isAgentModelNodeType } from './AgentModelWidgets';
import {
  AgentModelSelect as ControlAgentModelSelect,
  ControlAgentModeSelect,
  isControlAgentNodeType,
} from './ControlAgentWidgets';

const STATUS_RING: Record<string, string> = {
  running: 'ring-2 ring-blue-400 animate-pulse',
  success: 'ring-2 ring-emerald-400',
  error: 'ring-2 ring-red-500',
  blocked: 'ring-2 ring-amber-400',
  cached: 'ring-2 ring-slate-400',
  skipped: 'ring-2 ring-slate-300 opacity-70',
};

const VALID_ARTIFACT_KINDS = new Set<ArtifactKind>(['image', 'video', 'model3d', 'audio', 'vfx']);
const GENUI_KIND_TO_ARTIFACT: Record<string, ArtifactKind> = {
  Image: 'image',
  Video: 'video',
  Model3D: 'model3d',
};

function str(v: unknown): string | undefined {
  return typeof v === 'string' && v.trim() ? v : undefined;
}

function numOrNull(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v);
  return null;
}

/**
 * Assemble a professional artifact descriptor from a node's emitted media item
 * (``gen_ui``) and its ``executed`` metadata. Metadata wins for the kind and
 * structured fields (so audio renders an audio player even though it rides the
 * Image gen-ui socket); the gen-ui item supplies the canonical preview URL.
 */
function buildArtifactDescriptor(
  mediaItem: GenUiMediaItem | null,
  metadata: Record<string, unknown> | undefined,
): ArtifactDescriptor | null {
  const md = metadata ?? {};
  const mediaSrc = mediaItem?.src;
  // Per-node ``metadata.file_id`` wins over gen_ui src so passthrough and
  // re-run nodes never show a stale thumbnail from a shared gen_ui tree.
  const fileId =
    str(md.file_id) ||
    mediaItem?.fileId ||
    extractApiFilePreviewId(mediaSrc) ||
    extractApiFilePreviewId(str(md.src)) ||
    extractApiFilePreviewId(str(md.preview_url)) ||
    undefined;
  const src = fileId
    ? `/api/v1/files/${fileId}/preview`
    : mediaSrc ||
      str(md.src) ||
      str(md.preview_url) ||
      undefined;
  if (!src) return null;
  const mdKind = typeof md.kind === 'string' ? (md.kind as ArtifactKind) : undefined;
  const mediaKind = mediaItem?.kind;
  const kind: ArtifactKind =
    mdKind && VALID_ARTIFACT_KINDS.has(mdKind)
      ? mdKind
      : (mediaKind && GENUI_KIND_TO_ARTIFACT[mediaKind]) || 'image';
  return {
    kind,
    src,
    fileId,
    filename: str(md.filename),
    width: numOrNull(md.width),
    height: numOrNull(md.height),
    mime: str(md.mime),
    downloadUrl: str(md.download_url),
    fileSize: numOrNull(md.file_size),
    placeholder: md.placeholder === true,
  };
}

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
  const { t } = useTranslation();
  const nodeData = data as WorkflowNodeData;
  const def = useNodeDefinition(nodeData.nodeType);
  const { updateNodeData } = useReactFlow();
  const runState = useExecutionOverlay((s) => s.nodes[id]);
  const versionCount = useExecutionOverlay((s) => assetVersionCount(s.assetHistory, id));

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
  const mediaItem = mediaFromNodeRunState(runState);
  const isPreviewNode = nodeData.nodeType === 'Art.Preview';
  const isAgentNode =
    nodeData.nodeType.startsWith('Agent.') ||
    nodeData.nodeType === 'LLMCallNode' ||
    nodeData.nodeType === 'ScriptAgentNode' ||
    nodeData.nodeType === 'CodingAgentNode';
  const artifact = buildArtifactDescriptor(mediaItem, runState?.metadata);
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
        className="flex items-center justify-between gap-2 rounded-t-lg border-b border-border px-2 py-1.5"
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
          {versionCount > 1 && (
            <span
              className="rounded bg-sky-500/15 px-1 text-[9px] text-sky-600 dark:text-sky-400"
              title={t('execution.artBadge.versions', '{{count}} versions', { count: versionCount })}
            >
              {t('execution.artBadge.versionsShort', '{{count}}v', { count: versionCount })}
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
            nodeType={nodeData.nodeType}
            providerValue={
              (nodeData.values?.provider as string | undefined) ??
              (inputs.find((s) => s.id === 'provider')?.default as string | undefined)
            }
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

      {runState?.metadata && !isPreviewNode && <ArtNodeBadges metadata={runState.metadata} />}

      {artifact ? (
        <div
          key={`${id}:${artifact.fileId ?? artifact.src}`}
          className="border-t border-border bg-surface-sunken/50 px-2 py-2"
        >
          <NodeArtifactPreview
            descriptor={artifact}
            variant={isPreviewNode ? 'full' : 'compact'}
          />
        </div>
      ) : isPreviewNode && runState?.status === 'success' ? (
        <div className="border-t border-border bg-surface-sunken/50 px-2 py-3 text-center text-[10px] text-muted-foreground">
          {t('artifactPreview.empty', 'Connect an asset to preview it')}
        </div>
      ) : null}

      {runState?.preview != null && (
        <div className="max-h-32 overflow-auto border-t border-border bg-surface-sunken px-2 py-1 text-[10px] text-muted-foreground">
          {isAgentNode && runState.status === 'success' && (
            <div className="mb-0.5 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
              {t('execution.agentResult', 'Result')}
            </div>
          )}
          <PreviewRow preview={runState.preview} />
        </div>
      )}

      {runState?.error && (
        <div className="border-t border-border bg-red-50 px-2 py-1 text-[10px] text-red-600 dark:bg-red-950/30 dark:text-red-400">
          {runState.error}
        </div>
      )}
    </div>
  );
}

function InputSlotRow({
  nodeId,
  nodeType,
  providerValue,
  slot,
  index,
  connected,
  value,
  onChange,
}: {
  nodeId: string;
  nodeType: string;
  providerValue?: string;
  slot: InputSlot;
  index: number;
  connected: boolean;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const upstreamPreview = useUpstreamInputPreview(nodeId, slot.id);
  const isArtImage = ART_IMAGE_NODE_TYPES.has(nodeType);
  const artModel = isArtImage && slot.id === 'model';
  const artPreset = isArtImage && slot.id === 'preset';
  const agentModel = isAgentModelNodeType(nodeType) && slot.id === 'model';
  const controlMode = isControlAgentNodeType(nodeType) && slot.id === 'mode';
  const controlAgentModel =
    isControlAgentNodeType(nodeType) && slot.id === 'model';

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
        ) : artPreset && !connected ? (
          <ArtPresetSelect value={value} onChange={onChange} />
        ) : controlMode && !connected && slot.choices?.length ? (
          <ControlAgentModeSelect
            choices={slot.choices}
            value={value}
            onChange={onChange}
          />
        ) : controlAgentModel && !connected ? (
          <ControlAgentModelSelect value={value} onChange={onChange} />
        ) : agentModel && !connected ? (
          <AgentModelSelect value={value} onChange={onChange} />
        ) : artModel && !connected ? (
          <ArtModelSelect provider={providerValue} value={value} onChange={onChange} />
        ) : slot.widget && !slot.forceInput ? (
          <NodeWidget slot={slot} value={value} onChange={onChange} connected={connected} />
        ) : connected ? (
          <div className="text-[10px] italic text-muted-foreground">{slot.id} ← linked</div>
        ) : null}
      </div>
    </div>
  );
}

function num(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v);
  return null;
}

/**
 * Quality / refine badges surfaced from a node's ``executed`` metadata, so
 * the canvas shows self-evaluation outcomes (score, pass/fail, refine
 * iteration, provider, engine) inline on art nodes.
 */
function ArtNodeBadges({ metadata }: { metadata: Record<string, unknown> }) {
  const { t } = useTranslation();
  const score = num(metadata.quality_score);
  const passed = metadata.quality_passed;
  const iteration = num(metadata.refine_iteration ?? metadata.iteration);
  const provider = typeof metadata.provider === 'string' ? metadata.provider : null;
  const engine = typeof metadata.engine === 'string' ? metadata.engine : null;
  const placeholder = metadata.placeholder === true;

  const chips: { key: string; label: string; cls: string }[] = [];
  if (score != null) {
    const ok = passed === true || (passed == null && score >= 0.7);
    chips.push({
      key: 'score',
      label: `${t('execution.artBadge.quality', 'Quality')} ${score.toFixed(2)}`,
      cls: ok
        ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
        : 'bg-red-500/15 text-red-600 dark:text-red-400',
    });
  } else if (passed === true) {
    chips.push({ key: 'passed', label: t('execution.artBadge.passed', 'Passed'),
      cls: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400' });
  } else if (passed === false) {
    chips.push({ key: 'failed', label: t('execution.artBadge.failed', 'Below bar'),
      cls: 'bg-red-500/15 text-red-600 dark:text-red-400' });
  }
  if (iteration != null && iteration > 0) {
    chips.push({
      key: 'iter',
      label: `${t('execution.artBadge.refine', 'Refine')} #${iteration}`,
      cls: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
    });
  }
  if (provider) {
    chips.push({ key: 'provider', label: provider,
      cls: 'bg-slate-500/15 text-slate-600 dark:text-slate-300' });
  }
  if (engine) {
    chips.push({ key: 'engine', label: engine,
      cls: 'bg-indigo-500/15 text-indigo-600 dark:text-indigo-400' });
  }
  if (placeholder) {
    chips.push({ key: 'offline', label: t('execution.artBadge.offline', 'offline'),
      cls: 'bg-slate-400/15 text-slate-500' });
  }
  if (chips.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1 border-t border-border bg-surface-sunken/40 px-2 py-1.5">
      {chips.map((c) => (
        <span key={c.key} className={cn('rounded px-1.5 py-0.5 text-[9px] font-medium', c.cls)}>
          {c.label}
        </span>
      ))}
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
