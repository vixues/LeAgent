import {
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type RefObject,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Maximize2 } from 'lucide-react';
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type ColorMode,
  type Edge,
  type Node,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { parseStoredFlowDataForChatPreview } from '@/lib/parseFlowDataFromApi';
import type { FlowNode } from '@/stores/flow';
import { Button } from '@/components/ui/Button';
import { Modal, ModalHeader } from '@/components/ui/Modal';
import { cn } from '@/lib/utils';
import { ChatWorkflowMiniNode } from './ChatWorkflowMiniNode';
import './chat-workflow-flow.css';

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

/** Inline chat strip: map vertical wheel to horizontal pan. */
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

function MiniFlowInner({
  flowData,
  rootRef,
  mode,
}: {
  flowData: Record<string, unknown>;
  rootRef: RefObject<HTMLDivElement | null>;
  mode: 'inline' | 'overlay';
}) {
  const isOverlay = mode === 'overlay';
  const { nodes: parsedNodes, edges: parsedEdges } = useMemo(
    () => parseStoredFlowDataForChatPreview(flowData),
    [flowData],
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
            strokeWidth: 2,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14,
            height: 14,
            color: 'rgb(var(--color-text-secondary))',
          },
        } as Edge;
      }),
    [parsedEdges],
  );

  const colorMode = useChatPreviewColorMode();
  const maxZoom = isOverlay ? 2.5 : 1.25;
  const minZoom = isOverlay ? 0.04 : 0.08;

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
      panOnDrag
      minZoom={minZoom}
      maxZoom={maxZoom}
      proOptions={{ hideAttribution: true }}
      fitView
      defaultEdgeOptions={{
        type: 'smoothstep',
        style: {
          stroke: 'rgb(var(--color-text-secondary))',
          strokeWidth: 2,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color: 'rgb(var(--color-text-secondary))',
        },
      }}
    >
      {!isOverlay ? <HorizontalWheelPan rootRef={rootRef} /> : null}
      <FitBinder nodeCount={nodes.length} edgeCount={edges.length} maxZoom={maxZoom} />
      <Controls showInteractive={false} position="bottom-right" className="!m-2 !shadow-soft" />
      <Background variant={BackgroundVariant.Lines} gap={24} size={0.6} color="rgb(var(--color-border-subtle))" />
    </ReactFlow>
  );
}

export interface ChatWorkflowMiniGraphProps {
  flowData: Record<string, unknown>;
  /** Shown in the floating preview modal header (e.g. workflow title). */
  previewTitle?: string;
}

function ChatWorkflowMiniGraphInner({ flowData, previewTitle }: ChatWorkflowMiniGraphProps) {
  const { t } = useTranslation();
  const [floatingOpen, setFloatingOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const overlayRootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!floatingOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFloatingOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [floatingOpen]);

  const modalTitle =
    typeof previewTitle === 'string' && previewTitle.trim()
      ? previewTitle.trim()
      : t('chat.workflow.embedFallbackTitle');

  if (import.meta.env.MODE === 'test') {
    return (
      <div
        className="flex h-[300px] min-h-[300px] items-center justify-center rounded-2xl border border-dashed border-border-subtle bg-surface-raised/50 text-xs text-muted-foreground-tertiary"
        data-testid="chat-workflow-mini-graph-placeholder"
      >
        Workflow graph
      </div>
    );
  }

  return (
    <>
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-end px-0.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="shrink-0 gap-1.5"
            leftIcon={<Maximize2 className="h-3.5 w-3.5" aria-hidden />}
            aria-label={t('chat.workflow.expandFloatingPreview')}
            title={t('chat.workflow.expandFloatingHint')}
            onClick={() => setFloatingOpen(true)}
          >
            {t('chat.workflow.expandFloatingPreview')}
          </Button>
        </div>
        <div
          ref={rootRef}
          className="chat-workflow-flow h-[min(380px,62vh)] min-h-[300px] w-full overflow-hidden rounded-2xl border border-border-subtle bg-surface-sunken/50 dark:bg-surface-raised/20"
        >
          <ReactFlowProvider>
            <MiniFlowInner mode="inline" flowData={flowData} rootRef={rootRef} />
          </ReactFlowProvider>
        </div>
      </div>

      <Modal
        isOpen={floatingOpen}
        onClose={() => setFloatingOpen(false)}
        fullViewport
        size="2xl"
        className={cn(
          '!max-h-[92vh] !max-w-[min(96vw,1440px)] w-full !overflow-hidden',
          'flex min-h-0 flex-col p-0',
        )}
      >
        <ModalHeader onClose={() => setFloatingOpen(false)}>{modalTitle}</ModalHeader>
        <div className="px-3 pb-3 pt-1">
          <p className="pb-2 text-[11px] leading-snug text-muted-foreground-tertiary">
            {t('chat.workflow.expandFloatingHint')}
          </p>
          <div
            ref={overlayRootRef}
            className="chat-workflow-flow h-[min(76vh,calc(100dvh-10rem))] min-h-[400px] w-full overflow-hidden rounded-xl border border-border-subtle bg-surface-sunken/40 dark:bg-surface-raised/25"
          >
            <ReactFlowProvider>
              <MiniFlowInner mode="overlay" flowData={flowData} rootRef={overlayRootRef} />
            </ReactFlowProvider>
          </div>
        </div>
      </Modal>
    </>
  );
}

export const ChatWorkflowMiniGraph = memo(ChatWorkflowMiniGraphInner);
