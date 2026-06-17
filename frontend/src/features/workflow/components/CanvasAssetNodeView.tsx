import { memo, useCallback, useRef, useState } from 'react';
import { Handle, NodeResizer, Position, useReactFlow, type NodeProps } from '@xyflow/react';
import { Box, FileText, File as FileIcon, Minus, Plus, RotateCcw, Maximize2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import { useChatFileBlobUrl } from '@/hooks/useChatFileBlobUrl';
import {
  extractApiFilePreviewId,
  isInvalidApiFilePreviewRef,
} from '@/components/chat/media/chatMediaUtils';

import {
  type CanvasAssetNodeData,
  canvasAssetLabel,
  canvasAssetOutputWireType,
  canvasAssetSourceHandle,
  fitImageDisplaySize,
  IMAGE_NODE_MAX_EDGE,
  IMAGE_NODE_MIN_EDGE,
  MESH_ASSET_PREVIEW_HEIGHT,
  DEFAULT_MESH_ASSET_HEIGHT,
  DEFAULT_MESH_ASSET_WIDTH,
} from './canvasAsset';
import {
  CanvasMesh3DPreview,
  type CanvasMesh3DPreviewHandle,
} from './CanvasMesh3DPreview';
import { DEFAULT_SOCKET_COLORS } from '../graph/socketTypes';

function useAssetImageSrc(previewUrl?: string, fileId?: string): string | undefined {
  const raw = previewUrl || (fileId ? `/api/v1/files/${fileId}/preview` : '');
  const invalid = isInvalidApiFilePreviewRef(raw);
  const managedId = invalid ? null : extractApiFilePreviewId(raw);
  const { blobUrl } = useChatFileBlobUrl(managedId);
  if (invalid) return undefined;
  if (blobUrl) return blobUrl;
  return raw || undefined;
}

function isImageAsset(asset: CanvasAssetNodeData): boolean {
  return asset.assetKind === 'image' || Boolean(asset.mimeType?.startsWith('image/'));
}

function isMeshAsset(asset: CanvasAssetNodeData): boolean {
  return asset.assetKind === 'mesh3d';
}

/** Right-side output anchor — outside overflow-hidden so links stay grabbable. */
function AssetOutputHandle({
  handleId,
  wireType,
  color,
  label,
  showLabel = true,
  placement = 'center-right',
}: {
  handleId: string;
  wireType: string;
  color: string;
  label: string;
  showLabel?: boolean;
  placement?: 'center-right' | 'top-right';
}) {
  const handleStyle: React.CSSProperties =
    placement === 'top-right'
      ? { right: -14, top: 12, width: 11, height: 11, background: color }
      : {
          right: -14,
          top: '50%',
          width: 11,
          height: 11,
          background: color,
          transform: 'translateY(-50%)',
        };

  return (
    <>
      {showLabel && (
        <span
          className={cn(
            'pointer-events-none absolute z-10 rounded border border-border/80 bg-surface-elevated/95 px-1 py-0.5 text-[9px] font-medium shadow-sm',
            placement === 'top-right'
              ? 'right-3 top-2 translate-x-full'
              : 'right-3 top-1/2 -translate-y-1/2 translate-x-full',
          )}
          style={{ color }}
        >
          {label}
        </span>
      )}
      <Handle
        id={handleId}
        type="source"
        position={Position.Right}
        title={`${handleId}: ${wireType}`}
        className="!z-20 !border-2 !border-background"
        style={handleStyle}
      />
    </>
  );
}

/**
 * ComfyUI-style canvas input: drag image / text / file / mesh onto the graph.
 * Image & mesh nodes expose typed output handles on the right edge.
 */
function CanvasAssetNodeViewImpl({ id, data, selected }: NodeProps) {
  const asset = data as CanvasAssetNodeData;
  const { updateNode } = useReactFlow();
  const { t } = useTranslation('workflows');
  const meshPreviewRef = useRef<CanvasMesh3DPreviewHandle>(null);
  const [autoRotate, setAutoRotate] = useState(false);
  const handleId = canvasAssetSourceHandle(asset.assetKind);
  const wireType = canvasAssetOutputWireType(asset.assetKind, handleId);
  const color = DEFAULT_SOCKET_COLORS[wireType] ?? '#94a3b8';
  const imageSrc = useAssetImageSrc(asset.previewUrl, asset.fileId);
  const imageAsset = isImageAsset(asset);
  const meshAsset = isMeshAsset(asset);
  const title = canvasAssetLabel(asset);
  const handleLabel =
    wireType === 'IMAGE'
      ? t('canvasAsset.outputImage', { defaultValue: 'IMAGE' })
      : wireType === 'MESH3D'
        ? t('canvasAsset.outputMesh', { defaultValue: 'MESH3D' })
        : wireType;

  const onImageLoad = useCallback(
    (event: React.SyntheticEvent<HTMLImageElement>) => {
      if (!imageAsset || (asset.imageWidth && asset.imageHeight)) return;
      const img = event.currentTarget;
      const naturalWidth = img.naturalWidth;
      const naturalHeight = img.naturalHeight;
      if (naturalWidth <= 0 || naturalHeight <= 0) return;

      const fitted = fitImageDisplaySize(naturalWidth, naturalHeight);
      updateNode(id, {
        style: { width: fitted.width, height: fitted.height },
        data: {
          ...asset,
          imageWidth: naturalWidth,
          imageHeight: naturalHeight,
        },
      });
    },
    [asset, id, imageAsset, updateNode],
  );

  const maxResizeEdge = Math.max(
    IMAGE_NODE_MAX_EDGE,
    asset.imageWidth ?? IMAGE_NODE_MAX_EDGE,
    asset.imageHeight ?? IMAGE_NODE_MAX_EDGE,
  );

  if (meshAsset) {
    return (
      <div
        className={cn(
          'relative overflow-visible',
          selected && 'ring-2 ring-primary rounded-lg',
        )}
        style={{ width: DEFAULT_MESH_ASSET_WIDTH, height: DEFAULT_MESH_ASSET_HEIGHT }}
      >
        <div
          className="flex h-full flex-col overflow-hidden rounded-lg border border-border bg-surface-elevated shadow-md"
        >
          <div
            className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-2 py-1.5"
            style={{
              backgroundColor:
                'color-mix(in srgb, #FF8A65 22%, rgb(var(--color-surface-sunken)))',
            }}
          >
            <div className="flex min-w-0 items-center gap-1.5">
              <Box className="h-3.5 w-3.5 shrink-0 text-orange-400" aria-hidden />
              <span className="truncate text-xs font-semibold" title={title}>
                {title}
              </span>
            </div>
            <div className="nodrag flex shrink-0 items-center gap-0.5">
              <ToolbarBtn
                title={t('mesh3d.zoomOut', { defaultValue: 'Zoom out' })}
                onClick={() => meshPreviewRef.current?.zoomOut()}
              >
                <Minus className="h-3 w-3" />
              </ToolbarBtn>
              <ToolbarBtn
                title={t('mesh3d.zoomIn', { defaultValue: 'Zoom in' })}
                onClick={() => meshPreviewRef.current?.zoomIn()}
              >
                <Plus className="h-3 w-3" />
              </ToolbarBtn>
              <ToolbarBtn
                title={t('mesh3d.fitView', { defaultValue: 'Fit to view' })}
                onClick={() => meshPreviewRef.current?.fitView()}
              >
                <Maximize2 className="h-3 w-3" />
              </ToolbarBtn>
              <ToolbarBtn
                title={t('mesh3d.autoRotate', { defaultValue: 'Auto rotate' })}
                active={autoRotate}
                onClick={() => setAutoRotate((v) => !v)}
              >
                <RotateCcw className="h-3 w-3" />
              </ToolbarBtn>
            </div>
          </div>
          <div className="relative min-h-0 flex-1">
            <CanvasMesh3DPreview
              ref={meshPreviewRef}
              previewUrl={asset.previewUrl}
              fileId={asset.fileId}
              height={MESH_ASSET_PREVIEW_HEIGHT}
              autoRotate={autoRotate}
              className="h-full w-full rounded-none border-0"
            />
          </div>
        </div>
        <AssetOutputHandle
          handleId={handleId}
          wireType={wireType}
          color={color}
          label={handleLabel}
          showLabel={false}
        />
      </div>
    );
  }

  return (
    <div
      className={cn(
        'relative overflow-visible',
        selected && imageAsset && 'rounded-sm ring-2 ring-primary',
      )}
    >
      <NodeResizer
        isVisible={selected}
        minWidth={imageAsset ? IMAGE_NODE_MIN_EDGE : asset.assetKind === 'text' ? 120 : 100}
        minHeight={imageAsset ? IMAGE_NODE_MIN_EDGE : asset.assetKind === 'text' ? 64 : 80}
        maxWidth={imageAsset ? maxResizeEdge * 2 : 480}
        maxHeight={imageAsset ? maxResizeEdge * 2 : 360}
        keepAspectRatio={imageAsset}
        lineClassName="!border-primary-400"
        handleClassName="!h-2 !w-2 !rounded-sm !border-primary-400 !bg-surface"
      />
      <div
        className={cn(
          'relative h-full w-full overflow-hidden',
          imageAsset
            ? 'rounded-sm shadow-sm ring-1 ring-border/80'
            : 'rounded-lg shadow-md ring-1 ring-border/60 bg-surface-elevated',
          selected && !imageAsset && 'ring-2 ring-primary',
        )}
      >
        <AssetBody asset={asset} imageSrc={imageSrc} onImageLoad={onImageLoad} />

        {selected && !imageAsset && (
          <div className="pointer-events-none absolute inset-x-0 top-0 bg-gradient-to-b from-black/50 to-transparent px-2 py-1">
            <span className="truncate text-[10px] font-medium text-white/90">{title}</span>
          </div>
        )}
      </div>
      {(imageAsset || asset.assetKind === 'text' || asset.assetKind === 'file') && (
        <AssetOutputHandle
          handleId={handleId}
          wireType={wireType}
          color={color}
          label={handleLabel}
          showLabel={!imageAsset}
          placement={imageAsset ? 'top-right' : 'center-right'}
        />
      )}
    </div>
  );
}

function ToolbarBtn({
  children,
  title,
  active,
  onClick,
}: {
  children: React.ReactNode;
  title: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={cn(
        'rounded p-1 text-muted-foreground hover:bg-background/80 hover:text-foreground',
        active && 'bg-background/70 text-primary',
      )}
      title={title}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function AssetBody({
  asset,
  imageSrc,
  onImageLoad,
}: {
  asset: CanvasAssetNodeData;
  imageSrc: string | undefined;
  onImageLoad?: (event: React.SyntheticEvent<HTMLImageElement>) => void;
}) {
  if (asset.assetKind === 'text') {
    const text = (asset.textContent || '').trim() || '…';
    return (
      <div className="flex h-full w-full items-stretch p-2">
        <pre className="nodrag m-0 flex-1 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-relaxed text-foreground">
          {text}
        </pre>
      </div>
    );
  }

  if (isImageAsset(asset)) {
    if (!imageSrc) {
      return <div className="h-full w-full animate-pulse bg-surface-sunken" />;
    }
    return (
      <img
        src={imageSrc}
        alt={asset.fileName || 'image'}
        className="block h-full w-full select-none"
        draggable={false}
        onLoad={onImageLoad}
      />
    );
  }

  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-surface-sunken p-3 text-center">
      <FileIcon className="h-8 w-8 text-muted-foreground" aria-hidden />
      <span className="line-clamp-2 text-[11px] text-foreground">{asset.fileName || 'File'}</span>
      {asset.mimeType ? (
        <span className="text-[9px] uppercase tracking-wide text-muted-foreground">{asset.mimeType}</span>
      ) : null}
    </div>
  );
}

/** Tiny file chip when only an icon is needed in connected previews. */
export function FileAssetChip({ name, mime }: { name?: string; mime?: string }) {
  return (
    <div className="flex items-center gap-1.5 rounded-md border border-border bg-background/80 px-2 py-1 text-[10px]">
      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
      <span className="truncate">{name || 'File'}</span>
      {mime ? <span className="text-muted-foreground">({mime})</span> : null}
    </div>
  );
}

export const CanvasAssetNodeView = memo(CanvasAssetNodeViewImpl);
