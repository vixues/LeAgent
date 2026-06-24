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
  Panel,
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
import { ChatWorkflowRunPromptContext } from '@/components/chat/workflow/chatWorkflowRunContext';
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
  /** Active execution prompt id; enables live per-node status overlay. */
  runPromptId?: string | null;
  /** Extra icon buttons rendered below the default zoom/fit controls. */
  extraControlButtons?: React.ReactNode;
  /** Workflow content digest shown in the bottom-left corner of the pane. */
  digest?: string | null;
}

export function WorkflowMiniGraphCore({
  flowData,
  previewUi,
  rootRef,
  mode,
  showControls = true,
  showBackground = true,
  runPromptId = null,
  extraControlButtons,
  digest = null,
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
        const { markerEnd: _markerEnd, ...rest } = edge;
        return {
          ...rest,
          type: 'smoothstep',
          style: {
            ...edge.style,
            stroke: 'rgb(var(--color-text-tertiary))',
            strokeWidth: isCompact ? 1.5 : 1.75,
            strokeLinecap: 'round',
          },
        } as Edge;
      }),
    [parsedEdges, isCompact],
  );

  const colorMode = useChatPreviewColorMode();
  const maxZoom = isOverlay ? 2.5 : isCompact ? 1.1 : 1.25;
  const minZoom = isOverlay ? 0.04 : isCompact ? 0.06 : 0.08;

  return (
    <ChatWorkflowRunPromptContext.Provider value={runPromptId}>
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
          stroke: 'rgb(var(--color-text-tertiary))',
          strokeWidth: isCompact ? 1.5 : 1.75,
          strokeLinecap: 'round',
        },
      }}
    >
      {!isOverlay && !isCompact ? <HorizontalWheelPan rootRef={rootRef} /> : null}
      <FitBinder nodeCount={nodes.length} edgeCount={edges.length} maxZoom={maxZoom} />
      {showControls && !isCompact ? (
        <Controls showInteractive={false} position="bottom-right" className="!m-2 !shadow-soft">
          {extraControlButtons}
        </Controls>
      ) : null}
      {showBackground ? (
        <Background
          variant={BackgroundVariant.Lines}
          gap={isCompact ? 18 : 24}
          size={0.6}
          color="rgb(var(--color-border-subtle))"
        />
      ) : null}
      {digest && !isCompact ? (
        <Panel position="bottom-left" className="!m-2 pointer-events-none">
          <span
            className="font-mono text-[10px] text-muted-foreground-tertiary/80"
            title={digest}
          >
            {digest.length <= 8 ? digest : `${digest.slice(0, 4)}…${digest.slice(-4)}`}
          </span>
        </Panel>
      ) : null}
    </ReactFlow>
    </ChatWorkflowRunPromptContext.Provider>
  );
}
