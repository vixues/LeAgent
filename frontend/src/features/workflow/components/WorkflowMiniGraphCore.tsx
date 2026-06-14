import {
  useEffect,
  useMemo,
  useSyncExternalStore,
  type RefObject,
} from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  ReactFlow,
  useReactFlow,
  type ColorMode,
  type Edge,
  type Node,
  type NodeTypes,
} from '@xyflow/react';

import { parseStoredFlowDataForChatPreview } from '@/lib/parseFlowDataFromApi';
import type { FlowEdge, FlowNode } from '@/stores/flow';
import { ChatWorkflowMiniNode } from '@/components/chat/workflow/ChatWorkflowMiniNode';
import '@/components/chat/workflow/chat-workflow-flow.css';
import '@xyflow/react/dist/style.css';

const miniNodeTypes = {
  generic: ChatWorkflowMiniNode,
  default: ChatWorkflowMiniNode,
} satisfies NodeTypes;

function useChatPreviewColorMode(): ColorMode {
  return useSyncExternalStore(
    (cb) => {
      const el = document.documentElement;
      const obs = new MutationObserver(cb);
      obs.observe(el, { attributes: true, attributeFilter: ['class'] });
      return () => obs.disconnect();
    },
    () => (document.documentElement.classList.contains('dark') ? 'dark' : 'light'),
    () => 'light',
  );
}

function FitBinder({
  nodeCount,
  edgeCount,
  maxZoom,
}: {
  nodeCount: number;
  edgeCount: number;
  maxZoom: number;
}) {
  const rf = useReactFlow();
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      rf.fitView({ padding: 0.12, maxZoom, minZoom: 0.08 });
    });
    return () => cancelAnimationFrame(id);
  }, [rf, nodeCount, edgeCount, maxZoom]);
  return null;
}

/** Inline strip: map vertical wheel to horizontal pan. */
function HorizontalWheelPan({ rootRef }: { rootRef: RefObject<HTMLDivElement | null> }) {
  const rf = useReactFlow();

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const pane = root.querySelector('.react-flow__pane');
    if (!pane || !(pane instanceof HTMLElement)) return;

    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey) return;
      const v = rf.getViewport();
      const norm = e.deltaMode === 1 ? 16 : 1;
      const delta = (e.deltaY + e.deltaX) * norm;
      if (delta === 0) return;
      e.preventDefault();
      rf.setViewport({ x: v.x - delta * 0.55, y: v.y, zoom: v.zoom });
    };

    pane.addEventListener('wheel', onWheel, { passive: false });
    return () => pane.removeEventListener('wheel', onWheel);
  }, [rf, rootRef]);

  return null;
}

export interface TemplatePreviewUi {
  nodes?: FlowNode[];
  edges?: FlowEdge[];
}

function flowDataFromPreviewUi(previewUi: TemplatePreviewUi): Record<string, unknown> {
  return {
    ui: {
      nodes: previewUi.nodes ?? [],
      edges: previewUi.edges ?? [],
    },
  };
}

export interface WorkflowMiniGraphCoreProps {
  flowData?: Record<string, unknown> | null;
  previewUi?: TemplatePreviewUi | null;
  rootRef: RefObject<HTMLDivElement | null>;
  mode: 'inline' | 'overlay' | 'compact';
  showControls?: boolean;
  showBackground?: boolean;
}

export function WorkflowMiniGraphCore({
  flowData,
  previewUi,
  rootRef,
  mode,
  showControls = true,
  showBackground = true,
}: WorkflowMiniGraphCoreProps) {
  const isOverlay = mode === 'overlay';
  const isCompact = mode === 'compact';

  const resolvedFlowData = useMemo(() => {
    if (previewUi?.nodes?.length) {
      return flowDataFromPreviewUi(previewUi);
    }
    return flowData ?? {};
  }, [flowData, previewUi]);

  const { nodes: parsedNodes, edges: parsedEdges } = useMemo(
    () => parseStoredFlowDataForChatPreview(resolvedFlowData),
    [resolvedFlowData],
  );

  const nodes = useMemo(
    () =>
      (parsedNodes as FlowNode[]).map((n) => ({
        ...n,
        type: n.type === 'generic' ? 'generic' : 'default',
      })) as Node[],
    [parsedNodes],
  );

  const edges = useMemo(
    () =>
      parsedEdges.map((e) => {
        const edge = e as Edge;
        return {
          ...edge,
          type: 'smoothstep',
          style: {
            ...edge.style,
            stroke: 'rgb(var(--color-text-secondary))',
            strokeWidth: isCompact ? 1.75 : 2,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: isCompact ? 12 : 14,
            height: isCompact ? 12 : 14,
            color: 'rgb(var(--color-text-secondary))',
          },
        } as Edge;
      }),
    [parsedEdges, isCompact],
  );

  const colorMode = useChatPreviewColorMode();
  const maxZoom = isOverlay ? 2.5 : isCompact ? 1.1 : 1.25;
  const minZoom = isOverlay ? 0.04 : isCompact ? 0.06 : 0.08;

  return (
    <ReactFlow
      className="chat-workflow-flow-inner"
      colorMode={colorMode}
      nodes={nodes}
      edges={edges}
      nodeTypes={miniNodeTypes}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      panOnScroll={false}
      zoomOnScroll={isOverlay}
      zoomOnPinch
      zoomOnDoubleClick={isOverlay}
      panOnDrag={!isCompact}
      minZoom={minZoom}
      maxZoom={maxZoom}
      proOptions={{ hideAttribution: true }}
      fitView
      defaultEdgeOptions={{
        type: 'smoothstep',
        style: {
          stroke: 'rgb(var(--color-text-secondary))',
          strokeWidth: isCompact ? 1.75 : 2,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: isCompact ? 12 : 14,
          height: isCompact ? 12 : 14,
          color: 'rgb(var(--color-text-secondary))',
        },
      }}
    >
      {!isOverlay && !isCompact ? <HorizontalWheelPan rootRef={rootRef} /> : null}
      <FitBinder nodeCount={nodes.length} edgeCount={edges.length} maxZoom={maxZoom} />
      {showControls && !isCompact ? (
        <Controls showInteractive={false} position="bottom-right" className="!m-2 !shadow-soft" />
      ) : null}
      {showBackground ? (
        <Background
          variant={BackgroundVariant.Lines}
          gap={isCompact ? 18 : 24}
          size={0.6}
          color="rgb(var(--color-border-subtle))"
        />
      ) : null}
    </ReactFlow>
  );
}
