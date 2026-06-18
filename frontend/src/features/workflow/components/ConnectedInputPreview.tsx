import { useMemo } from 'react';
import { useStore } from '@xyflow/react';

import { mediaFromNodeRunState } from '@/components/canvas/genUi/genUiMedia';
import type { GenUiMediaItem } from '@/components/canvas/genUi/genUiMedia';

import {
  type CanvasAssetNodeData,
  canvasAssetPreview,
  isCanvasAssetNode,
} from './canvasAsset';
import { useExecutionOverlay } from '../store/executionOverlay';
import type { WorkflowNodeData } from '../graph/serialization';
import { NodeMediaPreview } from './NodeMediaPreview';
import { CanvasMesh3DPreview } from './CanvasMesh3DPreview';
import { FileAssetChip } from './CanvasAssetNodeView';

export interface InputPreviewDescriptor {
  kind: 'media' | 'text' | 'file';
  media?: GenUiMediaItem;
  text?: string;
  fileName?: string;
  mimeType?: string;
}

function previewFromLoadMeshValues(values: Record<string, unknown> | undefined): InputPreviewDescriptor | null {
  const file = values?.file;
  if (typeof file !== 'string' || !file.trim()) return null;
  return {
    kind: 'media',
    media: { kind: 'Model3D', src: `/api/v1/files/${file}/preview` },
  };
}
function previewFromLoadImageValues(values: Record<string, unknown> | undefined): InputPreviewDescriptor | null {
  const file = values?.file;
  if (typeof file !== 'string' || !file.trim()) return null;
  return {
    kind: 'media',
    media: { kind: 'Image', src: `/api/v1/files/${file}/preview` },
  };
}

/**
 * Resolve a compact preview for a connected input by walking the incoming edge
 * to its source node (canvas asset, LoadImage, or a node with execution UI).
 */
export function useUpstreamInputPreview(
  nodeId: string,
  slotId: string,
): InputPreviewDescriptor | null {
  const edge = useStore((s) =>
    s.edges.find((e) => e.target === nodeId && (e.targetHandle === slotId || !e.targetHandle)),
  );
  const sourceNode = useStore((s) => {
    if (!edge) return undefined;
    const fromLookup = (s as { nodeLookup?: Map<string, unknown> }).nodeLookup?.get(edge.source);
    if (fromLookup) return fromLookup as typeof s.nodes[number];
    return s.nodes.find((n) => n.id === edge.source);
  });
  const runState = useExecutionOverlay((s) =>
    edge?.source ? s.nodes[edge.source] : undefined,
  );

  return useMemo(() => {
    if (!sourceNode || !edge) return null;

    if (isCanvasAssetNode(sourceNode)) {
      const data = sourceNode.data as CanvasAssetNodeData;
      if (data.assetKind === 'text') {
        return { kind: 'text', text: data.textContent || '' };
      }
      const media = canvasAssetPreview(data);
      if (media) return { kind: 'media', media };
      return {
        kind: 'file',
        fileName: data.fileName,
        mimeType: data.mimeType,
      };
    }

    const processed = mediaFromNodeRunState(runState);
    if (processed) return { kind: 'media', media: processed };

    if (sourceNode.type === 'workflow') {
      const wf = sourceNode.data as WorkflowNodeData;
      if (wf.nodeType === 'LoadImage') {
        return previewFromLoadImageValues(wf.values);
      }
      if (wf.nodeType === 'LoadMesh3D') {
        return previewFromLoadMeshValues(wf.values);
      }
    }

    return null;
  }, [sourceNode, edge, runState]);
}

export function ConnectedInputPreview({ descriptor }: { descriptor: InputPreviewDescriptor }) {
  if (descriptor.kind === 'text') {
    const text = (descriptor.text || '').trim();
    if (!text) return null;
    return (
      <div className="max-h-20 overflow-auto rounded border border-border/60 bg-background/60 px-1.5 py-1 text-[10px] leading-snug text-foreground">
        {text.length > 280 ? `${text.slice(0, 280)}…` : text}
      </div>
    );
  }

  if (descriptor.kind === 'file') {
    return <FileAssetChip name={descriptor.fileName} mime={descriptor.mimeType} />;
  }

  if (descriptor.media) {
    if (descriptor.media.kind === 'Model3D') {
      return (
        <div className="overflow-hidden rounded border border-border/60 bg-background/40">
          <CanvasMesh3DPreview previewUrl={descriptor.media.src} height={120} />
        </div>
      );
    }
    return (
      <div className="overflow-hidden rounded border border-border/60 bg-background/40">
        <NodeMediaPreview item={descriptor.media} />
      </div>
    );
  }

  return null;
}
