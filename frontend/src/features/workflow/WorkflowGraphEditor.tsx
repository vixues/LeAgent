import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Background,
  BackgroundVariant,
  ConnectionMode,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type IsValidConnection,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Play, Save, Square, Plus, PanelLeft } from 'lucide-react';

import { apiClient } from '@/api/client';
import { Button } from '@/components/ui';
import { PageLoader } from '@/components/common/PageLoader';

import { NodeRegistryProvider } from './graph/registryContext';
import {
  toCanonicalDocument,
  fromStoredDocument,
  type EditorEdge,
  type EditorNode,
  type WorkflowNodeData,
} from './graph/serialization';
import { typesCompatible } from './graph/socketTypes';
import type { NodeDefinition, ObjectInfo } from './graph/objectInfo';
import { useObjectInfo } from './api/useObjectInfo';
import { useExecutionStream } from './api/useExecutionStream';
import { useExecutionOverlay } from './store/executionOverlay';
import { TypedNodeView } from './components/TypedNodeView';
import { WorkflowEdge } from './components/WorkflowEdge';
import { NodeSidebar } from './components/NodeSidebar';
import { NodeSearchPalette } from './components/NodeSearchPalette';
import { NodeInspector } from './components/NodeInspector';
import { ResumePanel } from './components/ResumePanel';

interface RunResponse {
  execution_id: string;
  prompt_id: string;
  status?: string;
}

function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `n_${Math.random().toString(36).slice(2)}`;
}

function defaultValues(def: NodeDefinition): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const slot of def.inputs) {
    if (slot.widget && slot.default !== undefined && !slot.forceInput) {
      values[slot.id] = slot.default;
    }
  }
  return values;
}

function EditorInner({ registry }: { registry: ObjectInfo }) {
  const { t } = useTranslation('workflows');
  const { id: routeId } = useParams<{ id?: string }>();
  const navigate = useNavigate();

  const [flowId, setFlowId] = useState<string | null>(
    routeId && routeId !== 'new' ? routeId : null,
  );
  const [name, setName] = useState('Untitled Workflow');
  const [nodes, setNodes, onNodesChange] = useNodesState<EditorNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<EditorEdge>([]);
  const [paletteAt, setPaletteAt] = useState<{ x: number; y: number } | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingFlow, setLoadingFlow] = useState(Boolean(flowId));
  const [error, setError] = useState<string | null>(null);
  const [promptId, setPromptId] = useState<string | null>(null);

  const rf = useReactFlow();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const overlayRunning = useExecutionOverlay((s) => s.running);
  const resetOverlay = useExecutionOverlay((s) => s.reset);
  useExecutionStream(promptId);

  // Load an existing flow into the editor.
  useEffect(() => {
    let cancelled = false;
    if (!flowId) {
      setLoadingFlow(false);
      return;
    }
    setLoadingFlow(true);
    apiClient
      .get<{ id: string; name: string; data?: string | null }>(`/workflow/flows/${flowId}`)
      .then((raw) => {
        if (cancelled) return;
        setName(raw.name || 'Untitled Workflow');
        const { nodes: n, edges: e } = fromStoredDocument(raw.data ?? null, registry.definitions);
        setNodes(n);
        setEdges(e);
        setLoadingFlow(false);
        window.requestAnimationFrame(() => rf.fitView({ padding: 0.2 }));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load workflow');
        setLoadingFlow(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flowId, registry]);

  const addNode = useCallback(
    (def: NodeDefinition, position?: { x: number; y: number }) => {
      const pos =
        position ??
        rf.screenToFlowPosition({
          x: (wrapperRef.current?.clientWidth ?? 800) / 2,
          y: (wrapperRef.current?.clientHeight ?? 600) / 2,
        });
      const node: EditorNode = {
        id: newId(),
        type: 'workflow',
        position: pos,
        data: {
          nodeType: def.type,
          label: def.displayName,
          category: def.category,
          description: def.description,
          values: defaultValues(def),
        } satisfies WorkflowNodeData,
      };
      setNodes((cur) => [...cur, node]);
    },
    [rf, setNodes],
  );

  const isValidConnection = useCallback<IsValidConnection>(
    (conn) => {
      if (!conn.source || !conn.target) return false;
      if (conn.source === conn.target) return false;
      const sourceNode = rf.getNode(conn.source) as Node<WorkflowNodeData> | undefined;
      const targetNode = rf.getNode(conn.target) as Node<WorkflowNodeData> | undefined;
      const sourceDef = registry.definitions[sourceNode?.data.nodeType ?? ''];
      const targetDef = registry.definitions[targetNode?.data.nodeType ?? ''];
      const outType =
        sourceDef?.outputs.find((o) => o.id === conn.sourceHandle)?.type ??
        sourceDef?.outputs[0]?.type ??
        '*';
      const inType =
        targetDef?.inputs.find((i) => i.id === conn.targetHandle)?.type ??
        targetDef?.inputs[0]?.type ??
        '*';
      return typesCompatible(outType, inType);
    },
    [rf, registry],
  );

  const onConnect = useCallback(
    (conn: Connection) => {
      const sourceNode = rf.getNode(conn.source) as Node<WorkflowNodeData> | undefined;
      const sourceDef = registry.definitions[sourceNode?.data.nodeType ?? ''];
      const color =
        sourceDef?.outputs.find((o) => o.id === conn.sourceHandle)?.color ??
        sourceDef?.outputs[0]?.color;
      const edge: Edge = {
        ...conn,
        id: `e-${conn.source}-${conn.sourceHandle ?? '0'}-${conn.target}-${conn.targetHandle ?? '0'}`,
        type: 'workflow',
        data: { color },
      };
      setEdges((eds) => addEdge(edge, eds));
    },
    [rf, registry, setEdges],
  );

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const type = event.dataTransfer.getData('application/leagent-node');
      const def = registry.definitions[type];
      if (!def) return;
      const position = rf.screenToFlowPosition({ x: event.clientX, y: event.clientY });
      addNode(def, position);
    },
    [registry, rf, addNode],
  );

  const handleSave = useCallback(async (): Promise<string | null> => {
    setSaving(true);
    setError(null);
    try {
      const doc = toCanonicalDocument({
        id: flowId ?? '',
        name,
        nodes,
        edges,
        viewport: rf.getViewport(),
        definitions: registry.definitions,
      });
      if (flowId) {
        await apiClient.put(`/workflow/flows/${flowId}`, { name, data: doc });
        return flowId;
      }
      const created = await apiClient.post<{ id: string }>('/workflow/flows', {
        name,
        data: doc,
      });
      const newFlowId = String(created.id);
      setFlowId(newFlowId);
      navigate(`/workflows/${newFlowId}`, { replace: true });
      return newFlowId;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
      return null;
    } finally {
      setSaving(false);
    }
  }, [flowId, name, nodes, edges, rf, registry, navigate]);

  const handleRun = useCallback(async () => {
    if (nodes.length === 0) {
      setError(t('flowEditor.runNeedNodes', 'Add at least one node before running'));
      return;
    }
    const id = await handleSave();
    if (!id) return;
    resetOverlay();
    try {
      const res = await apiClient.post<RunResponse>(`/workflow/flows/${id}/run`, {
        input_data: {},
      });
      setPromptId(res.prompt_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Run failed');
    }
  }, [nodes.length, handleSave, resetOverlay, t]);

  const handleStop = useCallback(async () => {
    if (!promptId) return;
    try {
      await apiClient.post(`/workflow/prompts/${promptId}/cancel`, {});
    } catch {
      /* best effort */
    }
    setPromptId(null);
  }, [promptId]);

  const nodeTypes = useMemo(() => ({ workflow: TypedNodeView }), []);
  const edgeTypes = useMemo(() => ({ workflow: WorkflowEdge }), []);

  const selectedNodes = nodes.filter((n) => n.selected);
  const selectedNode = selectedNodes.length === 1 ? selectedNodes[0] : undefined;

  if (loadingFlow) {
    return (
      <div className="flex h-full items-center justify-center">
        <PageLoader message={t('flowEditor.loadingFlow', 'Loading workflow...')} />
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 border-b border-border bg-surface px-3 py-2">
        <button
          className="rounded p-1.5 text-muted-foreground hover:bg-accent"
          onClick={() => setSidebarCollapsed((c) => !c)}
          title={t('flowEditor.toggleSidebar', 'Toggle node panel')}
        >
          <PanelLeft className="h-4 w-4" />
        </button>
        <input
          className="w-64 rounded border border-transparent bg-transparent px-2 py-1 text-sm font-medium hover:border-border focus:border-border focus:outline-none"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <div className="ml-auto flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            leftIcon={<Plus className="h-4 w-4" />}
            onClick={() =>
              setPaletteAt({
                x: (wrapperRef.current?.clientWidth ?? 800) / 2,
                y: (wrapperRef.current?.clientHeight ?? 600) / 2,
              })
            }
          >
            {t('flowEditor.addNode', 'Add node')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            leftIcon={<Save className="h-4 w-4" />}
            onClick={() => void handleSave()}
            disabled={saving}
          >
            {t('flowEditor.save', 'Save')}
          </Button>
          {overlayRunning ? (
            <Button size="sm" variant="danger" leftIcon={<Square className="h-4 w-4" />} onClick={handleStop}>
              {t('flowEditor.stop', 'Stop')}
            </Button>
          ) : (
            <Button size="sm" leftIcon={<Play className="h-4 w-4" />} onClick={handleRun}>
              {t('flowEditor.run', 'Run')}
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <NodeSidebar registry={registry} collapsed={sidebarCollapsed} onAdd={addNode} />
        <div
          ref={wrapperRef}
          className="relative min-h-0 flex-1"
          onDrop={onDrop}
          onDragOver={(e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
          }}
          onDoubleClick={(e) => {
            const target = e.target as HTMLElement;
            if (target.classList.contains('react-flow__pane')) {
              setPaletteAt({ x: e.clientX, y: e.clientY });
            }
          }}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            isValidConnection={isValidConnection}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            connectionMode={ConnectionMode.Loose}
            defaultEdgeOptions={{ type: 'workflow' }}
            deleteKeyCode={['Delete', 'Backspace']}
            multiSelectionKeyCode={['Shift', 'Meta', 'Control']}
            selectionKeyCode="Shift"
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
            <Controls />
            <MiniMap pannable zoomable />
            <Panel position="bottom-center">
              <span className="rounded bg-surface/80 px-2 py-1 text-[10px] text-muted-foreground">
                {t('flowEditor.paletteHint', 'Double-click canvas to search nodes')}
              </span>
            </Panel>
          </ReactFlow>

          {paletteAt && (
            <NodeSearchPalette
              registry={registry}
              onClose={() => setPaletteAt(null)}
              onSelect={(def) => {
                addNode(def, rf.screenToFlowPosition(paletteAt));
                setPaletteAt(null);
              }}
            />
          )}

          <ResumePanel />
        </div>

        {selectedNode && (
          <NodeInspector
            node={selectedNode}
            onClose={() =>
              setNodes((cur) =>
                cur.map((n) =>
                  n.id === selectedNode.id ? { ...n, selected: false } : n,
                ),
              )
            }
          />
        )}
      </div>
    </div>
  );
}

/**
 * ComfyUI-style workflow editor built on React Flow + the custom graph engine
 * (typed sockets, inline widgets, `/object_info` registry, live execution
 * overlay). Replaces the legacy `FlowPage` canvas internals.
 */
export function WorkflowGraphEditor() {
  const { t } = useTranslation('workflows');
  const { data: registry, isLoading, isError } = useObjectInfo();

  if (isLoading || !registry) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center bg-background">
        <PageLoader message={t('flowEditor.loadingNodes', 'Loading node catalog...')} />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center bg-background text-sm text-muted-foreground">
        {t('flowEditor.loadNodesFailed', 'Failed to load the node catalog.')}
      </div>
    );
  }

  return (
    <NodeRegistryProvider value={registry}>
      <div className="flex min-h-0 flex-1 flex-col bg-background">
        <ReactFlowProvider>
          <EditorInner registry={registry} />
        </ReactFlowProvider>
      </div>
    </NodeRegistryProvider>
  );
}

export default WorkflowGraphEditor;
