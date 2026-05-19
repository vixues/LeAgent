import { useCallback, useRef, useState, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  BackgroundVariant,
  ConnectionMode,
  SelectionMode,
  NodeTypes,
  EdgeTypes,
  OnInit,
  ReactFlowInstance,
  Connection,
  Edge,
  IsValidConnection,
  OnSelectionChangeParams,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Layers,
  Grid3X3,
  MousePointer2,
  ZoomIn,
  ZoomOut,
  LayoutGrid,
  ArrowLeftRight,
  ArrowUpDown,
} from 'lucide-react';

import { useFlowStore, FlowNode, FlowEdge } from '../../../stores/flow';
import { GenericNode } from '../../../CustomNodes/GenericNode';
import { DefaultEdge } from '../../../CustomEdges/DefaultEdge';
import { useAddComponent, ComponentDefinition } from '../../../hooks/flows/useAddComponent';
import { cn } from '../../../lib/utils';
import { layoutNodes, type LayoutDirection } from '../../../lib/workflowLayout';
import { useTranslation } from 'react-i18next';

const nodeTypes: NodeTypes = {
  generic: GenericNode,
};

const edgeTypes: EdgeTypes = {
  default: DefaultEdge,
};

const proOptions = { hideAttribution: true };

const CATEGORY_COLORS: Record<string, string> = {
  doc: '#f97316',
  web: '#3b82f6',
  data: '#22c55e',
  llm: '#0284c7',
  email: '#ef4444',
  notification: '#eab308',
  delay: '#6b7280',
  condition: '#0369a1',
  loop: '#06b6d4',
  webhook: '#ec4899',
  transform: '#14b8a6',
  trigger: '#f59e0b',
};

interface FlowCanvasProps {
  className?: string;
  onNodeDoubleClick?: (node: FlowNode) => void;
}

export function FlowCanvas({ className, onNodeDoubleClick }: FlowCanvasProps) {
  const { t } = useTranslation();
  const reactFlowRef = useRef<ReactFlowInstance<FlowNode, FlowEdge> | null>(null);
  const [showGrid, setShowGrid] = useState(true);
  const [showMiniMap, setShowMiniMap] = useState(true);
  const [snapToGrid] = useState(true);
  const [selectedCount, setSelectedCount] = useState(0);
  const [layoutDirection, setLayoutDirection] = useState<LayoutDirection>('LR');

  const {
    nodes,
    edges,
    setNodes,
    onNodesChange,
    onEdgesChange,
    onConnect,
    selectNode,
    saveToHistory,
  } = useFlowStore();

  const { addComponentFromDrop } = useAddComponent();

  const onInit: OnInit<FlowNode, FlowEdge> = useCallback((instance) => {
    reactFlowRef.current = instance;
    if (nodes.length > 0) {
      setTimeout(() => instance.fitView({ padding: 0.2, maxZoom: 1 }), 0);
    }
  }, [nodes.length]);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: FlowNode) => {
      selectNode(node.id);
    },
    [selectNode]
  );

  const onNodeDoubleClickHandler = useCallback(
    (_: React.MouseEvent, node: FlowNode) => {
      selectNode(node.id);
      onNodeDoubleClick?.(node);
    },
    [selectNode, onNodeDoubleClick]
  );

  const onPaneClick = useCallback(() => {
    selectNode(null);
  }, [selectNode]);

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();

      const componentData = event.dataTransfer.getData('application/json');
      if (!componentData) return;

      try {
        const component: ComponentDefinition = JSON.parse(componentData);
        addComponentFromDrop(component, event);
      } catch {
        console.error('Failed to parse dropped component data');
      }
    },
    [addComponentFromDrop]
  );

  const isValidConnection: IsValidConnection = useCallback(
    (connection: Connection | Edge) => {
      const sourceNode = nodes.find((n) => n.id === connection.source);
      const targetNode = nodes.find((n) => n.id === connection.target);

      if (!sourceNode || !targetNode) return false;
      if (connection.source === connection.target) return false;

      const existingConnection = edges.find(
        (e) =>
          e.source === connection.source &&
          e.target === connection.target &&
          e.sourceHandle === connection.sourceHandle &&
          e.targetHandle === connection.targetHandle
      );
      if (existingConnection) return false;

      return true;
    },
    [nodes, edges]
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      saveToHistory();
      onConnect(connection);
    },
    [onConnect, saveToHistory]
  );

  const onSelectionChange = useCallback((params: OnSelectionChangeParams) => {
    setSelectedCount(params.nodes.length);
  }, []);

  const nodeColor = useCallback((node: FlowNode) => {
    const category = node.data?.category;
    return (category && CATEGORY_COLORS[category]) || '#64748b';
  }, []);

  const defaultEdgeOptions = useMemo(
    () => ({
      type: 'default',
      animated: false,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 15,
        height: 15,
        color: '#94a3b8',
      },
      style: {
        strokeWidth: 2,
        stroke: '#94a3b8',
      },
    }),
    []
  );

  const handleFitView = useCallback(() => {
    reactFlowRef.current?.fitView({ padding: 0.2, maxZoom: 1 });
  }, []);

  const handleZoomIn = useCallback(() => {
    reactFlowRef.current?.zoomIn({ duration: 200 });
  }, []);

  const handleZoomOut = useCallback(() => {
    reactFlowRef.current?.zoomOut({ duration: 200 });
  }, []);

  const handleRelayout = useCallback(
    (direction: LayoutDirection = layoutDirection) => {
      if (nodes.length === 0) return;
      saveToHistory();
      const { nodes: laidOut } = layoutNodes(nodes, edges, { direction });
      setNodes(laidOut);
      // Wait a tick so ReactFlow has time to pick up the new positions
      // before we ask it to fit the viewport.
      setTimeout(() => {
        reactFlowRef.current?.fitView({ padding: 0.2, maxZoom: 1, duration: 300 });
      }, 50);
    },
    [nodes, edges, setNodes, saveToHistory, layoutDirection],
  );

  const handleToggleDirection = useCallback(() => {
    const next: LayoutDirection = layoutDirection === 'LR' ? 'TB' : 'LR';
    setLayoutDirection(next);
    handleRelayout(next);
  }, [layoutDirection, handleRelayout]);

  return (
    <div className={cn('h-full w-full relative', className)}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={handleConnect}
        onInit={onInit}
        onNodeClick={onNodeClick}
        onNodeDoubleClick={onNodeDoubleClickHandler}
        onPaneClick={onPaneClick}
        onDragOver={onDragOver}
        onDrop={onDrop}
        onSelectionChange={onSelectionChange}
        isValidConnection={isValidConnection}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        connectionMode={ConnectionMode.Loose}
        selectionMode={SelectionMode.Partial}
        proOptions={proOptions}
        fitView
        snapToGrid={snapToGrid}
        snapGrid={[15, 15]}
        deleteKeyCode={['Backspace', 'Delete']}
        multiSelectionKeyCode={['Shift', 'Meta']}
        panOnScroll
        selectionOnDrag
        panOnDrag={[1, 2]}
        zoomOnDoubleClick={false}
        minZoom={0.1}
        maxZoom={2}
        className="bg-surface-sunken"
        defaultEdgeOptions={defaultEdgeOptions}
        connectionLineStyle={{ stroke: '#0284c7', strokeWidth: 2 }}
        connectionLineContainerStyle={{ zIndex: 1000 }}
      >
        {showGrid && (
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color="currentColor"
            className="text-border-subtle"
          />
        )}

        <Controls
          position="bottom-left"
          showZoom={false}
          showFitView={false}
          showInteractive={false}
          className="!bg-transparent !shadow-none !border-none"
        />

        <Panel position="bottom-left" className="!m-4">
          <div className="flex items-center gap-1 p-1 bg-surface rounded-lg shadow-lg border border-border">
            <button
              onClick={handleZoomOut}
              className="p-2 rounded-md text-muted-foreground hover:bg-surface-sunken transition-colors"
              title={t('flowEditor.zoomOut')}
            >
              <ZoomOut className="w-4 h-4" />
            </button>
            <button
              onClick={handleZoomIn}
              className="p-2 rounded-md text-muted-foreground hover:bg-surface-sunken transition-colors"
              title={t('flowEditor.zoomIn')}
            >
              <ZoomIn className="w-4 h-4" />
            </button>
            <button
              onClick={handleFitView}
              className="p-2 rounded-md text-muted-foreground hover:bg-surface-sunken transition-colors"
              title={t('flowEditor.fitView')}
            >
              <MousePointer2 className="w-4 h-4" />
            </button>
            <div className="w-px h-6 bg-border mx-1" />
            <button
              onClick={() => setShowGrid(!showGrid)}
              className={cn(
                'p-2 rounded-md transition-colors',
                showGrid
                  ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400'
                  : 'text-muted-foreground hover:bg-surface-sunken'
              )}
              title={t('flowEditor.toggleGrid')}
            >
              <Grid3X3 className="w-4 h-4" />
            </button>
            <button
              onClick={() => setShowMiniMap(!showMiniMap)}
              className={cn(
                'p-2 rounded-md transition-colors',
                showMiniMap
                  ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400'
                  : 'text-muted-foreground hover:bg-surface-sunken'
              )}
              title={t('flowEditor.toggleMinimap')}
            >
              <Layers className="w-4 h-4" />
            </button>
            <div className="w-px h-6 bg-border mx-1" />
            <button
              onClick={() => handleRelayout()}
              disabled={nodes.length === 0}
              className="p-2 rounded-md text-muted-foreground hover:bg-surface-sunken transition-colors disabled:opacity-40 disabled:pointer-events-none"
              title={t('flowEditor.relayout')}
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={handleToggleDirection}
              className={cn(
                'p-2 rounded-md transition-colors',
                'text-muted-foreground hover:bg-surface-sunken',
              )}
              title={`${t('flowEditor.toggleDirection')} (${layoutDirection})`}
            >
              {layoutDirection === 'LR' ? (
                <ArrowLeftRight className="w-4 h-4" />
              ) : (
                <ArrowUpDown className="w-4 h-4" />
              )}
            </button>
          </div>
        </Panel>

        {showMiniMap && (
          <MiniMap
            position="bottom-right"
            nodeColor={nodeColor}
            maskColor="rgba(0, 0, 0, 0.1)"
            className="!bg-surface !border-border !shadow-lg !rounded-lg overflow-hidden"
            pannable
            zoomable
            style={{ width: 150, height: 100 }}
          />
        )}

        {selectedCount > 1 && (
          <Panel position="top-center" className="!m-4">
            <div className="px-3 py-1.5 rounded-full shadow-lg border border-primary-200/80 dark:border-primary-700 bg-primary-50 dark:bg-primary-900/25 text-primary-800 dark:text-primary-200 text-sm font-medium">
              {t('flowEditor.nodesSelected', { count: selectedCount })}
            </div>
          </Panel>
        )}

        {nodes.length === 0 && (
          <Panel position="top-center" className="!m-0 !inset-0 flex items-center justify-center pointer-events-none">
            <div className="text-center">
              <div className="w-16 h-16 rounded-2xl bg-surface-sunken flex items-center justify-center mx-auto mb-4">
                <Layers className="w-8 h-8 text-muted-foreground-tertiary" />
              </div>
              <h3 className="text-lg font-medium text-foreground mb-2">
                {t('flowEditor.emptyCanvasTitle')}
              </h3>
              <p className="text-sm text-muted-foreground max-w-xs">
                {t('flowEditor.emptyCanvasHint')}
              </p>
            </div>
          </Panel>
        )}
      </ReactFlow>
    </div>
  );
}

export default FlowCanvas;
