import { memo, useCallback, useMemo } from 'react';
import { Handle, Position, useReactFlow, type NodeProps } from '@xyflow/react';
import { useTranslation } from 'react-i18next';

import { useChatFileBlobUrl } from '@/hooks/useChatFileBlobUrl';
import {
  extractApiFilePreviewId,
  isInvalidApiFilePreviewRef,
} from '@/components/chat/media/chatMediaUtils';

import { useNodeDefinition } from '../../graph/registryContext';
import type { WorkflowNodeData } from '../../graph/serialization';
import { DEFAULT_SOCKET_COLORS } from '../../graph/socketTypes';
import { useExecutionOverlay } from '../../store/executionOverlay';
import { useUpstreamInputPreview } from '../ConnectedInputPreview';
import { buildQwenViewPrompt, distanceToZoom } from './cameraAngles';
import { CameraAngleSelects, MultiAngleCameraViewport } from './MultiAngleCameraViewport';
import { NodeShell } from './NodeShell';

function usePreviewMediaUrl(descriptor: ReturnType<typeof useUpstreamInputPreview>): string | undefined {
  const raw = descriptor?.kind === 'media' ? descriptor.media?.src : undefined;
  const invalid = useMemo(() => isInvalidApiFilePreviewRef(raw || ''), [raw]);
  const managedId = useMemo(
    () => (invalid || !raw ? null : extractApiFilePreviewId(raw)),
    [raw, invalid],
  );
  const { blobUrl } = useChatFileBlobUrl(managedId);
  if (invalid || !raw) return undefined;
  return blobUrl || raw;
}

function CameraControlNodeViewImpl({ id, data, selected }: NodeProps) {
  const nodeData = data as WorkflowNodeData;
  const def = useNodeDefinition('Art.CameraControl');
  const { updateNodeData } = useReactFlow();
  const { t } = useTranslation('workflows');
  const runState = useExecutionOverlay((s) => s.nodes[id]);
  const imagePreview = useUpstreamInputPreview(id, 'image');
  const meshPreview = useUpstreamInputPreview(id, 'mesh');
  const imageUrl = usePreviewMediaUrl(imagePreview);
  const meshUrl = usePreviewMediaUrl(meshPreview);

  const values = nodeData.values ?? {};
  const horizontalAngle = Number(values.horizontal_angle ?? values.azimuth ?? 45);
  const verticalAngle = Number(values.vertical_angle ?? values.elevation ?? 0);
  const zoom = Number(values.zoom ?? distanceToZoom(Number(values.distance ?? 5)));
  const cameraView = Boolean(values.camera_view);
  const viewportHeight = 200;
  const previewScale = 1;

  const setValues = useCallback(
    (patch: Record<string, unknown>) => {
      updateNodeData(id, { values: { ...values, ...patch, preset: 'custom' } });
    },
    [id, updateNodeData, values],
  );

  const qwenPrompt = buildQwenViewPrompt(horizontalAngle, verticalAngle, zoom);
  const accent = DEFAULT_SOCKET_COLORS.OBJECT;
  const outputs = def?.outputs ?? [];

  return (
    <NodeShell
      title={nodeData.label || def?.displayName || '3D Camera Control'}
      accent={accent}
      selected={selected}
      status={runState?.status}
      mode={nodeData.mode}
    >
      <div className="flex flex-col gap-2 p-2">
        <div className="relative">
          <Handle
            id="image"
            type="target"
            position={Position.Left}
            title="image: IMAGE"
            style={{
              left: -14,
              top: 28,
              width: 11,
              height: 11,
              background: DEFAULT_SOCKET_COLORS.IMAGE,
              border: '2px solid var(--color-background, #fff)',
            }}
          />
          <Handle
            id="mesh"
            type="target"
            position={Position.Left}
            title="mesh: MESH3D"
            style={{
              left: -14,
              top: 52,
              width: 11,
              height: 11,
              background: DEFAULT_SOCKET_COLORS.MESH3D,
              border: '2px solid var(--color-background, #fff)',
            }}
          />
          <MultiAngleCameraViewport
            imageUrl={meshUrl ? undefined : imageUrl}
            meshUrl={meshUrl}
            horizontalAngle={horizontalAngle}
            verticalAngle={verticalAngle}
            zoom={zoom}
            cameraView={cameraView}
            height={viewportHeight}
            subjectScale={previewScale}
            onChange={(next) =>
              setValues({
                horizontal_angle: next.horizontalAngle,
                vertical_angle: next.verticalAngle,
                zoom: next.zoom,
                azimuth: next.horizontalAngle,
                elevation: next.verticalAngle,
                distance: 1.5 + (next.zoom / 10) * 6.5,
              })
            }
          />
        </div>

        <CameraAngleSelects
          horizontalAngle={horizontalAngle}
          verticalAngle={verticalAngle}
          zoom={zoom}
          labels={{
            horizontal: t('cameraControl.horizontal', { defaultValue: 'H' }),
            vertical: t('cameraControl.vertical', { defaultValue: 'V' }),
            distance: t('cameraControl.distance', { defaultValue: 'Z' }),
          }}
          onAzimuthPreset={(d) => setValues({ horizontal_angle: d, azimuth: d })}
          onElevationPreset={(d) => setValues({ vertical_angle: d, elevation: d })}
          onDistancePreset={(z) => setValues({ zoom: z, distance: 1.5 + (z / 10) * 6.5 })}
        />

        <div className="flex flex-col gap-2 border-t border-border/50 pt-2">
          <SliderRow
            label={t('cameraControl.azimuthDeg', { defaultValue: 'Azimuth' })}
            value={horizontalAngle}
            min={0}
            max={360}
            unit="°"
            onChange={(v) => setValues({ horizontal_angle: v, azimuth: v })}
          />
          <SliderRow
            label={t('cameraControl.elevationDeg', { defaultValue: 'Elevation' })}
            value={verticalAngle}
            min={-30}
            max={60}
            unit="°"
            onChange={(v) => setValues({ vertical_angle: v, elevation: v })}
          />
          <SliderRow
            label={t('cameraControl.zoom', { defaultValue: 'Distance / Zoom' })}
            value={zoom}
            min={0}
            max={10}
            step={0.1}
            onChange={(v) => setValues({ zoom: v, distance: 1.5 + (v / 10) * 6.5 })}
          />
        </div>

        <label className="nodrag flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <input
            type="checkbox"
            checked={cameraView}
            onChange={(e) => setValues({ camera_view: e.target.checked })}
          />
          {t('cameraControl.cameraView', { defaultValue: 'Camera view mode' })}
        </label>

        <div className="rounded border border-border/60 bg-surface-sunken px-2 py-1">
          <span className="text-[9px] uppercase text-muted-foreground">
            {t('cameraControl.promptOut', { defaultValue: 'Prompt' })}
          </span>
          <p className="mt-0.5 font-mono text-[10px] leading-snug text-foreground">{qwenPrompt}</p>
        </div>
      </div>

      <div className="relative border-t border-border px-2 py-2">
        {outputs.map((slot, index) => (
          <div key={slot.id} className="relative text-right text-[10px] text-muted-foreground">
            {slot.id}
            <Handle
              id={slot.id}
              type="source"
              position={Position.Right}
              title={`${slot.id}: ${slot.type}`}
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

/** Full-width slider row: label | track | value */
function SliderRow({
  label,
  value,
  min,
  max,
  step = 1,
  unit = '',
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  onChange: (v: number) => void;
}) {
  const display =
    step < 1 ? value.toFixed(2) : Number.isInteger(value) ? String(value) : value.toFixed(1);
  return (
    <label className="nodrag flex items-center gap-2">
      <span className="w-[4.5rem] shrink-0 truncate text-[10px] text-muted-foreground" title={label}>
        {label}
      </span>
      <input
        type="range"
        className="min-w-0 flex-1 accent-primary"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <span className="w-10 shrink-0 text-right text-[10px] tabular-nums text-foreground">
        {display}
        {unit}
      </span>
    </label>
  );
}

export const CameraControlNodeView = memo(CameraControlNodeViewImpl);
