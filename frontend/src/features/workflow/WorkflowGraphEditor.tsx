import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
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
import {
  Play,
  Save,
  Square,
  Plus,
  PanelLeft,
  PanelRight,
  Group,
  Ungroup,
  Combine,
  AlignStartVertical,
  AlignCenterVertical,
  AlignEndVertical,
  AlignStartHorizontal,
  AlignCenterHorizontal,
  AlignEndHorizontal,
  AlignHorizontalDistributeCenter,
  AlignVerticalDistributeCenter,
} from 'lucide-react';

import { apiClient } from '@/api/client';
import { Button } from '@/components/ui';
import { PageLoader } from '@/components/common/PageLoader';
import { cn } from '@/lib/utils';

import { useShortcutsStore, initializeShortcutListener } from '@/stores/shortcutsStore';

import { NodeRegistryProvider } from './graph/registryContext';
import { useGraphHistory } from './graph/useGraphHistory';
import {
  toCanonicalDocument,
  fromStoredDocument,
  type EditorEdge,
  type EditorNode,
  type WorkflowNodeData,
} from './graph/serialization';
import { typesCompatible, DEFAULT_SOCKET_COLORS } from './graph/socketTypes';
import type { NodeDefinition, ObjectInfo } from './graph/objectInfo';
import { useObjectInfo } from './api/useObjectInfo';
import { useExecutionStream } from './api/useExecutionStream';
import { useExecutionOverlay } from './store/executionOverlay';
import { useConnectionDrag } from './store/connectionDrag';
import type { WorkflowInputSpec } from './genui/inputsToGenUiTree';
import type { WorkflowOutputSpec } from './genui/outputsToGenUiTree';
import { TypedNodeView } from './components/TypedNodeView';
import { CanvasAssetNodeView } from './components/CanvasAssetNodeView';
import { RerouteNodeView } from './components/RerouteNodeView';
import { GroupNodeView } from './components/GroupNodeView';
import { WorkflowEdge } from './components/WorkflowEdge';
import { NodeSidebar } from './components/NodeSidebar';
import { NodeSearchPalette, type PaletteTypeFilter } from './components/NodeSearchPalette';
import { NodeInspector } from './components/NodeInspector';
import { ResumePanel } from './components/ResumePanel';
import { WorkflowRunPanel } from './components/WorkflowRunPanel';
import { WorkflowIOPanel } from './components/WorkflowIOPanel';
import {
  type CanvasAssetNodeData,
  CANVAS_ASSET_NODE_TYPE,
  buildCanvasAssetNode,
  canvasAssetOutputWireType,
  canvasAssetSourceHandle,
  classifyDroppedFile,
  DEFAULT_MESH_ASSET_HEIGHT,
  DEFAULT_MESH_ASSET_WIDTH,
  fitImageDisplaySize,
  measureImageFile,
  readFileAsText,
  uploadWorkflowAsset,
} from './components/canvasAsset';

interface RunResponse {
  execution_id: string;
  prompt_id: string;
  status?: string;
}

function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `n_${Math.random().toString(36).slice(2)}`;
}

const nodeW = (n: EditorNode) => n.measured?.width ?? 240;
const nodeH = (n: EditorNode) => n.measured?.height ?? 120;

interface DanglingLink {
  nodeId: string;
  handleId: string | null;
  handleType: 'source' | 'target';
  /** Wire type of the dangling end. */
  type: string;
}

function isInputSpec(v: unknown): v is WorkflowInputSpec {
  return Boolean(v) && typeof v === 'object' && typeof (v as { name?: unknown }).name === 'string';
}

function isOutputSpec(v: unknown): v is WorkflowOutputSpec {
  return Boolean(v) && typeof v === 'object' && typeof (v as { name?: unknown }).name === 'string';
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
  const { t } = useTranslation();
  const { id: routeId } = useParams<{ id?: string }>();
  const navigate = useNavigate();

  const [flowId, setFlowId] = useState<string | null>(
    routeId && routeId !== 'new' ? routeId : null,
  );

  // Keep flowId in sync when the route changes while mounted (e.g. drilling
  // into a subworkflow navigates /workflows/A → /workflows/B in place).
  useEffect(() => {
    const next = routeId && routeId !== 'new' ? routeId : null;
    setFlowId((cur) => (cur === next ? cur : next));
  }, [routeId]);
  const [name, setName] = useState('Untitled Workflow');
  const [nodes, setNodes, onNodesChange] = useNodesState<EditorNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<EditorEdge>([]);
  const [paletteAt, setPaletteAt] = useState<{ x: number; y: number } | null>(null);
  /** Set when the palette opened from a link release (filters + auto-connects). */
  const [paletteLink, setPaletteLink] = useState<DanglingLink | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingFlow, setLoadingFlow] = useState(Boolean(flowId));
  const [error, setError] = useState<string | null>(null);
  const [docInputs, setDocInputs] = useState<WorkflowInputSpec[]>([]);
  const [docOutputs, setDocOutputs] = useState<WorkflowOutputSpec[]>([]);
  const [rightPanel, setRightPanel] = useState<'run' | 'io' | null>(null);
  const [canvasDragActive, setCanvasDragActive] = useState(false);
  const [assetDropBusy, setAssetDropBusy] = useState(false);
  const [searchParams] = useSearchParams();

  useEffect(() => {
    if (searchParams.get('panel') === 'run') {
      setRightPanel('run');
    }
  }, [searchParams]);

  const rf = useReactFlow();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const overlayRunning = useExecutionOverlay((s) => s.running);
  const resetOverlay = useExecutionOverlay((s) => s.reset);
  // Subscribe to whichever run is active — started from the toolbar or from
  // the GenUI run form (which calls `useExecutionOverlay.start` itself).
  const promptId = useExecutionOverlay((s) => s.promptId);
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
        const stored = fromStoredDocument(raw.data ?? null, registry.definitions);
        setNodes(stored.nodes);
        setEdges(stored.edges);
        setDocInputs(stored.inputs.filter(isInputSpec));
        setDocOutputs(stored.outputs.filter(isOutputSpec));
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
    (def: NodeDefinition, position?: { x: number; y: number }): string => {
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
      return node.id;
    },
    [rf, setNodes],
  );

  const addCanvasAsset = useCallback(
    (
      position: { x: number; y: number },
      data: CanvasAssetNodeData,
      size?: { width: number; height: number },
    ) => {
      const node = buildCanvasAssetNode(newId(), position, data, size);
      setNodes((cur) => [...cur, node as EditorNode]);
      return node.id;
    },
    [setNodes],
  );

  const addFileAsset = useCallback(
    async (position: { x: number; y: number }, file: File) => {
      const kind = classifyDroppedFile(file);
      if (kind === 'text') {
        const text = await readFileAsText(file);
        addCanvasAsset(position, {
          assetKind: 'text',
          textContent: text,
          fileName: file.name,
          label: file.name,
        });
        return;
      }
      const uploaded = await uploadWorkflowAsset(file);
      const isImage = kind === 'image';
      const isMesh = kind === 'mesh3d';
      let imageWidth: number | undefined;
      let imageHeight: number | undefined;
      let size: { width: number; height: number } | undefined;
      if (isImage) {
        const dims = await measureImageFile(file);
        imageWidth = dims.width;
        imageHeight = dims.height;
        size = fitImageDisplaySize(dims.width, dims.height);
      } else if (isMesh) {
        size = { width: DEFAULT_MESH_ASSET_WIDTH, height: DEFAULT_MESH_ASSET_HEIGHT };
      }
      addCanvasAsset(
        position,
        {
          assetKind: isImage ? 'image' : isMesh ? 'mesh3d' : 'file',
          fileId: uploaded.id,
          fileName: uploaded.filename || file.name,
          mimeType: uploaded.mime_type || file.type,
          previewUrl: uploaded.preview_url,
          imageWidth,
          imageHeight,
        },
        size,
      );
    },
    [addCanvasAsset],
  );

  const addTextAsset = useCallback(
    (position: { x: number; y: number }, text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      addCanvasAsset(position, {
        assetKind: 'text',
        textContent: trimmed,
        label: trimmed.length > 24 ? `${trimmed.slice(0, 24)}…` : trimmed,
      });
    },
    [addCanvasAsset],
  );

  const canvasAssetWireType = useCallback((node: Node | undefined, handleId: string | null): string => {
    if (!node || node.type !== CANVAS_ASSET_NODE_TYPE) return '*';
    const data = node.data as CanvasAssetNodeData;
    return canvasAssetOutputWireType(data.assetKind, handleId);
  }, []);

  const isValidConnection = useCallback<IsValidConnection>(
    (conn) => {
      if (!conn.source || !conn.target) return false;
      if (conn.source === conn.target) return false;
      const sourceNode = rf.getNode(conn.source);
      const targetNode = rf.getNode(conn.target) as Node<WorkflowNodeData> | undefined;
      let outType = '*';
      if (sourceNode?.type === CANVAS_ASSET_NODE_TYPE) {
        outType = canvasAssetWireType(sourceNode, conn.sourceHandle);
      } else {
        const wfSource = sourceNode as Node<WorkflowNodeData> | undefined;
        const sourceDef = registry.definitions[wfSource?.data.nodeType ?? ''];
        outType =
          sourceDef?.outputs.find((o) => o.id === conn.sourceHandle)?.type ??
          sourceDef?.outputs[0]?.type ??
          '*';
      }
      const targetDef = registry.definitions[targetNode?.data.nodeType ?? ''];
      const inType =
        targetDef?.inputs.find((i) => i.id === conn.targetHandle)?.type ??
        targetDef?.inputs[0]?.type ??
        '*';
      // ARRAY inputs act as "list of downstream type" in wiring: allow linking
      // any upstream type (wildcard) and let the node validate at runtime.
      if (inType === 'ARRAY') return true;
      return typesCompatible(outType, inType);
    },
    [rf, registry, canvasAssetWireType],
  );

  const onConnect = useCallback(
    (conn: Connection) => {
      const sourceNode = rf.getNode(conn.source);
      let color: string | undefined;
      if (sourceNode?.type === CANVAS_ASSET_NODE_TYPE) {
        const data = sourceNode.data as CanvasAssetNodeData;
        const wire = canvasAssetOutputWireType(data.assetKind, conn.sourceHandle);
        color = DEFAULT_SOCKET_COLORS[wire];
      } else {
        const wfSource = sourceNode as Node<WorkflowNodeData> | undefined;
        const sourceDef = registry.definitions[wfSource?.data.nodeType ?? ''];
        color =
          sourceDef?.outputs.find((o) => o.id === conn.sourceHandle)?.color ??
          sourceDef?.outputs[0]?.color;
      }
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

  // ── Link-drag lifecycle: compat dimming, drop-on-node, link-release search ──
  const dragRef = useRef<DanglingLink | null>(null);

  const wireTypeFor = useCallback(
    (nodeId: string, handleId: string | null, handleType: 'source' | 'target'): string => {
      const node = rf.getNode(nodeId);
      if (!node) return '*';
      if (node.type === CANVAS_ASSET_NODE_TYPE) {
        const data = node.data as CanvasAssetNodeData;
        if (handleType === 'source') {
          return canvasAssetOutputWireType(data.assetKind, handleId ?? canvasAssetSourceHandle(data.assetKind));
        }
        return '*';
      }
      const wf = node as Node<WorkflowNodeData>;
      const def = registry.definitions[wf.data.nodeType ?? ''];
      if (!def) return '*';
      const slots = handleType === 'source' ? def.outputs : def.inputs;
      return slots.find((s) => s.id === handleId)?.type ?? slots[0]?.type ?? '*';
    },
    [rf, registry],
  );

  /** Connect a dangling link to the first compatible slot of `otherNodeId`. */
  const autoConnect = useCallback(
    (drag: DanglingLink, otherNodeId: string) => {
      const other = rf.getNode(otherNodeId) as Node<WorkflowNodeData> | undefined;
      const otherDef = registry.definitions[other?.data.nodeType ?? ''];
      if (!otherDef) return;
      if (drag.handleType === 'source') {
        const slot = otherDef.inputs.find((s) => typesCompatible(drag.type, s.type));
        if (!slot) return;
        onConnect({
          source: drag.nodeId,
          sourceHandle: drag.handleId,
          target: otherNodeId,
          targetHandle: slot.id,
        });
      } else {
        const slot = otherDef.outputs.find((s) => typesCompatible(s.type, drag.type));
        if (!slot) return;
        onConnect({
          source: otherNodeId,
          sourceHandle: slot.id,
          target: drag.nodeId,
          targetHandle: drag.handleId,
        });
      }
    },
    [rf, registry, onConnect],
  );

  const onConnectStart = useCallback(
    (
      _event: MouseEvent | TouchEvent,
      params: { nodeId: string | null; handleId: string | null; handleType: 'source' | 'target' | null },
    ) => {
      if (!params.nodeId || !params.handleType) return;
      const type = wireTypeFor(params.nodeId, params.handleId, params.handleType);
      dragRef.current = {
        nodeId: params.nodeId,
        handleId: params.handleId,
        handleType: params.handleType,
        type,
      };
      useConnectionDrag.getState().start(type, params.handleType === 'source' ? 'out' : 'in');
    },
    [wireTypeFor],
  );

  const onConnectEnd = useCallback(
    (event: MouseEvent | TouchEvent) => {
      const drag = dragRef.current;
      dragRef.current = null;
      useConnectionDrag.getState().clear();
      if (!drag) return;

      const target = event.target as HTMLElement | null;
      if (!target) return;
      // Released on a handle → React Flow's onConnect already handled it.
      if (target.closest('.react-flow__handle')) return;

      // Released on a node body → connect to its first compatible slot.
      const nodeEl = target.closest('.react-flow__node') as HTMLElement | null;
      if (nodeEl) {
        const overId = nodeEl.getAttribute('data-id');
        if (overId && overId !== drag.nodeId) autoConnect(drag, overId);
        return;
      }

      // Released on empty canvas → type-filtered node search + auto-connect.
      if (target.classList.contains('react-flow__pane')) {
        const point =
          'clientX' in event
            ? { x: event.clientX, y: event.clientY }
            : event.changedTouches.length > 0
              ? { x: event.changedTouches[0]!.clientX, y: event.changedTouches[0]!.clientY }
              : null;
        if (point) {
          setPaletteLink(drag);
          setPaletteAt(point);
        }
      }
    },
    [autoConnect],
  );

  const onDrop = useCallback(
    async (event: React.DragEvent) => {
      event.preventDefault();
      setCanvasDragActive(false);
      const position = rf.screenToFlowPosition({ x: event.clientX, y: event.clientY });

      const nodeType = event.dataTransfer.getData('application/leagent-node');
      if (nodeType) {
        const def = registry.definitions[nodeType];
        if (def) addNode(def, position);
        return;
      }

      const files = Array.from(event.dataTransfer.files ?? []);
      const plain = event.dataTransfer.getData('text/plain');

      if (files.length === 0 && plain.trim()) {
        addTextAsset(position, plain);
        return;
      }

      if (!files.length) return;

      setAssetDropBusy(true);
      setError(null);
      try {
        for (let i = 0; i < files.length; i++) {
          const file = files[i]!;
          const at = { x: position.x + i * 28, y: position.y + i * 28 };
          await addFileAsset(at, file);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : t('flowEditor.assetDropFailed', 'Failed to add asset'));
      } finally {
        setAssetDropBusy(false);
      }
    },
    [registry, rf, addNode, addFileAsset, addTextAsset, t],
  );

  const onDragOverCanvas = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    const hasFiles = Array.from(event.dataTransfer.types).includes('Files');
    const hasText = Array.from(event.dataTransfer.types).includes('text/plain');
    const hasNode = Array.from(event.dataTransfer.types).includes('application/leagent-node');
    if (hasFiles || hasText) {
      event.dataTransfer.dropEffect = 'copy';
      setCanvasDragActive(true);
    } else if (hasNode) {
      event.dataTransfer.dropEffect = 'move';
      setCanvasDragActive(false);
    }
  }, []);

  const onDragLeaveCanvas = useCallback((event: React.DragEvent) => {
    if (event.currentTarget === event.target) {
      setCanvasDragActive(false);
    }
  }, []);

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
        inputs: docInputs,
        outputs: docOutputs,
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
  }, [flowId, name, nodes, edges, rf, registry, navigate, docInputs, docOutputs]);

  const handleRun = useCallback(async () => {
    if (nodes.length === 0) {
      setError(t('flowEditor.runNeedNodes', 'Add at least one node before running'));
      return;
    }
    const id = await handleSave();
    if (!id) return;
    // Workflows with declared inputs run through the GenUI form in the
    // Run panel; parameterless workflows run immediately.
    if (docInputs.length > 0) {
      setRightPanel('run');
      return;
    }
    resetOverlay();
    try {
      const res = await apiClient.post<RunResponse>(`/workflow/flows/${id}/run`, {
        input_data: {},
      });
      useExecutionOverlay.getState().start(res.prompt_id);
      setRightPanel('run');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Run failed');
    }
  }, [nodes.length, handleSave, resetOverlay, docInputs.length, t]);

  const handleStop = useCallback(async () => {
    if (!promptId) return;
    try {
      await apiClient.post(`/workflow/prompts/${promptId}/cancel`, {});
    } catch {
      /* best effort */
    }
    resetOverlay();
  }, [promptId, resetOverlay]);

  const history = useGraphHistory({ nodes, edges, setNodes, setEdges });

  // Toggle ComfyUI-style execution modes on the selected nodes.
  const toggleMode = useCallback(
    (mode: 'mute' | 'bypass') => {
      setNodes((cur) =>
        cur.map((n) =>
          n.selected
            ? {
                ...n,
                data: { ...n.data, mode: n.data.mode === mode ? undefined : mode },
              }
            : n,
        ),
      );
    },
    [setNodes],
  );

  // ── ComfyUI parity: reroutes, group frames, align/distribute, subgraphs ──

  /** Double-click an edge to split it with a reroute waypoint. */
  const onEdgeDoubleClick = useCallback(
    (event: React.MouseEvent, edge: Edge) => {
      event.stopPropagation();
      const at = rf.screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const rerouteId = newId();
      setNodes((cur) => [
        ...cur,
        {
          id: rerouteId,
          type: 'reroute',
          position: { x: at.x - 8, y: at.y - 8 },
          data: { nodeType: '__reroute__', label: '', category: 'ui' },
        },
      ]);
      setEdges((eds) =>
        eds
          .filter((e) => e.id !== edge.id)
          .concat([
            {
              ...edge,
              id: `e-${edge.source}-${edge.sourceHandle ?? '0'}-${rerouteId}-in`,
              target: rerouteId,
              targetHandle: 'in',
            },
            {
              ...edge,
              id: `e-${rerouteId}-out-${edge.target}-${edge.targetHandle ?? '0'}`,
              source: rerouteId,
              sourceHandle: 'out',
            },
          ]),
      );
    },
    [rf, setNodes, setEdges],
  );

  /** Wrap the selected top-level nodes in a group frame. */
  const groupSelection = useCallback(() => {
    setNodes((cur) => {
      const selected = cur.filter((n) => n.selected && !n.parentId && n.type !== 'group');
      if (selected.length < 2) return cur;
      const PAD = 32;
      const HEADER = 30;
      const minX = Math.min(...selected.map((n) => n.position.x)) - PAD;
      const minY = Math.min(...selected.map((n) => n.position.y)) - PAD - HEADER;
      const maxX = Math.max(...selected.map((n) => n.position.x + nodeW(n))) + PAD;
      const maxY = Math.max(...selected.map((n) => n.position.y + nodeH(n))) + PAD;
      const groupId = newId();
      const frame: EditorNode = {
        id: groupId,
        type: 'group',
        position: { x: minX, y: minY },
        style: { width: maxX - minX, height: maxY - minY },
        selectable: true,
        data: { nodeType: '__group__', label: 'Group', category: 'ui' },
      };
      const ids = new Set(selected.map((n) => n.id));
      // React Flow requires parents to precede children in the array.
      return [
        frame,
        ...cur.map((n) =>
          ids.has(n.id)
            ? {
                ...n,
                parentId: groupId,
                position: { x: n.position.x - minX, y: n.position.y - minY },
                selected: false,
              }
            : n,
        ),
      ];
    });
  }, [setNodes]);

  /** Dissolve the selected group frames, restoring absolute child positions. */
  const ungroupSelection = useCallback(() => {
    setNodes((cur) => {
      const groups = cur.filter((n) => n.selected && n.type === 'group');
      if (groups.length === 0) return cur;
      const byId = new Map(groups.map((g) => [g.id, g]));
      return cur
        .filter((n) => !byId.has(n.id))
        .map((n) => {
          const parent = n.parentId ? byId.get(n.parentId) : undefined;
          if (!parent) return n;
          return {
            ...n,
            parentId: undefined,
            position: {
              x: n.position.x + parent.position.x,
              y: n.position.y + parent.position.y,
            },
          };
        });
    });
  }, [setNodes]);

  type AlignMode = 'left' | 'centerX' | 'right' | 'top' | 'centerY' | 'bottom';

  const alignSelection = useCallback(
    (mode: AlignMode) => {
      setNodes((cur) => {
        const sel = cur.filter((n) => n.selected && n.type !== 'group');
        if (sel.length < 2) return cur;
        const ids = new Set(sel.map((n) => n.id));
        let target = 0;
        switch (mode) {
          case 'left':
            target = Math.min(...sel.map((n) => n.position.x));
            break;
          case 'right':
            target = Math.max(...sel.map((n) => n.position.x + nodeW(n)));
            break;
          case 'centerX':
            target =
              sel.reduce((acc, n) => acc + n.position.x + nodeW(n) / 2, 0) / sel.length;
            break;
          case 'top':
            target = Math.min(...sel.map((n) => n.position.y));
            break;
          case 'bottom':
            target = Math.max(...sel.map((n) => n.position.y + nodeH(n)));
            break;
          case 'centerY':
            target =
              sel.reduce((acc, n) => acc + n.position.y + nodeH(n) / 2, 0) / sel.length;
            break;
        }
        return cur.map((n) => {
          if (!ids.has(n.id)) return n;
          const pos = { ...n.position };
          if (mode === 'left') pos.x = target;
          else if (mode === 'right') pos.x = target - nodeW(n);
          else if (mode === 'centerX') pos.x = target - nodeW(n) / 2;
          else if (mode === 'top') pos.y = target;
          else if (mode === 'bottom') pos.y = target - nodeH(n);
          else pos.y = target - nodeH(n) / 2;
          return { ...n, position: pos };
        });
      });
    },
    [setNodes],
  );

  const distributeSelection = useCallback(
    (axis: 'x' | 'y') => {
      setNodes((cur) => {
        const sel = cur
          .filter((n) => n.selected && n.type !== 'group')
          .sort((a, b) => (axis === 'x' ? a.position.x - b.position.x : a.position.y - b.position.y));
        if (sel.length < 3) return cur;
        const size = axis === 'x' ? nodeW : nodeH;
        const first = sel[0]!;
        const last = sel[sel.length - 1]!;
        const start = axis === 'x' ? first.position.x : first.position.y;
        const end = axis === 'x' ? last.position.x : last.position.y;
        const inner = sel.slice(1, -1);
        const innerTotal = inner.reduce((acc, n) => acc + size(n), 0);
        const gap = (end - (start + size(first)) - innerTotal) / (inner.length + 1);
        const targets = new Map<string, number>();
        let cursor = start + size(first) + gap;
        for (const n of inner) {
          targets.set(n.id, cursor);
          cursor += size(n) + gap;
        }
        return cur.map((n) => {
          const v = targets.get(n.id);
          if (v === undefined) return n;
          return {
            ...n,
            position: axis === 'x' ? { ...n.position, x: v } : { ...n.position, y: v },
          };
        });
      });
    },
    [setNodes],
  );

  /** Extract the selected nodes into a new flow and replace them with a SubworkflowNode. */
  const extractSubworkflow = useCallback(async () => {
    const sel = nodes.filter((n) => n.selected && n.type === 'workflow');
    if (sel.length < 2) return;
    const subDef = registry.definitions['SubworkflowNode'];
    if (!subDef) {
      setError(t('flowEditor.subgraphUnavailable', 'SubworkflowNode is not available'));
      return;
    }
    const ids = new Set(sel.map((n) => n.id));
    const innerEdges = edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    const detached = sel.map((n) => {
      const parent = n.parentId ? nodes.find((p) => p.id === n.parentId) : undefined;
      return {
        ...n,
        parentId: undefined,
        selected: false,
        position: parent
          ? { x: n.position.x + parent.position.x, y: n.position.y + parent.position.y }
          : n.position,
      };
    });
    try {
      const doc = toCanonicalDocument({
        id: '',
        name: `${name} — subgraph`,
        nodes: detached,
        edges: innerEdges,
        definitions: registry.definitions,
      });
      const created = await apiClient.post<{ id: string }>('/workflow/flows', {
        name: doc.name,
        data: doc,
      });
      const subId = String(created.id);
      const cx = detached.reduce((acc, n) => acc + n.position.x, 0) / detached.length;
      const cy = detached.reduce((acc, n) => acc + n.position.y, 0) / detached.length;
      const subNode: EditorNode = {
        id: newId(),
        type: 'workflow',
        position: { x: cx, y: cy },
        data: {
          nodeType: 'SubworkflowNode',
          label: doc.name,
          category: subDef.category,
          description: subDef.description,
          values: { ...defaultValues(subDef), subworkflow_id: subId },
        },
      };
      setNodes((cur) => [...cur.filter((n) => !ids.has(n.id)), subNode]);
      setEdges((eds) => eds.filter((e) => !ids.has(e.source) && !ids.has(e.target)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Subgraph extraction failed');
    }
  }, [nodes, edges, registry, name, setNodes, setEdges, t]);

  /** Drill into a subworkflow on double-click (ComfyUI subgraph navigation). */
  const onNodeDoubleClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      const data = node.data as WorkflowNodeData | undefined;
      if (data?.nodeType !== 'SubworkflowNode') return;
      const subId = (data.values as Record<string, unknown> | undefined)?.subworkflow_id;
      if (typeof subId === 'string' && subId) navigate(`/workflows/${subId}`);
    },
    [navigate],
  );

  // Keep the latest editor actions in a ref so the keymap registers once.
  const actionsRef = useRef({
    save: handleSave,
    run: handleRun,
    stop: handleStop,
    undo: history.undo,
    redo: history.redo,
    copy: history.copySelection,
    paste: history.paste,
    toggleMode,
    openPalette: () =>
      setPaletteAt({
        x: (wrapperRef.current?.clientWidth ?? 800) / 2,
        y: (wrapperRef.current?.clientHeight ?? 600) / 2,
      }),
    fitView: () => rf.fitView({ padding: 0.2 }),
    toggleSidebar: () => setSidebarCollapsed((c) => !c),
  });
  actionsRef.current = {
    ...actionsRef.current,
    save: handleSave,
    run: handleRun,
    stop: handleStop,
    undo: history.undo,
    redo: history.redo,
    copy: history.copySelection,
    paste: history.paste,
    toggleMode,
  };

  // Wire the shared shortcuts keymap (`useShortcutsStore`) + editor-local
  // bindings (Alt+M mute, Alt+B bypass, Ctrl+Shift+V paste-with-connect).
  useEffect(() => {
    const store = useShortcutsStore.getState();
    const guarded =
      (fn: () => void, allowInInputs = false) =>
      (ctx: { isInputFocused: boolean }) => {
        if (ctx.isInputFocused && !allowInInputs) return false;
        fn();
        return true;
      };
    const bindings: Array<[string, (ctx: { isInputFocused: boolean }) => boolean | void]> = [
      ['editor:undo', guarded(() => actionsRef.current.undo())],
      ['editor:redo', guarded(() => actionsRef.current.redo())],
      ['editor:copy', guarded(() => actionsRef.current.copy())],
      ['editor:paste', guarded(() => actionsRef.current.paste(false))],
      ['file:save', guarded(() => void actionsRef.current.save(), true)],
      ['flow:run', guarded(() => void actionsRef.current.run())],
      ['flow:stop', guarded(() => void actionsRef.current.stop())],
      ['flow:add-node', guarded(() => actionsRef.current.openPalette())],
      ['view:zoom-fit', guarded(() => actionsRef.current.fitView())],
      ['view:toggle-sidebar', guarded(() => actionsRef.current.toggleSidebar())],
    ];
    for (const [action, handler] of bindings) store.registerHandler(action, handler);
    const removeListener = initializeShortcutListener();

    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable
      ) {
        return;
      }
      if (e.altKey && !e.ctrlKey && !e.metaKey && e.key.toLowerCase() === 'm') {
        e.preventDefault();
        actionsRef.current.toggleMode('mute');
      } else if (e.altKey && !e.ctrlKey && !e.metaKey && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        actionsRef.current.toggleMode('bypass');
      } else if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'v') {
        e.preventDefault();
        actionsRef.current.paste(true);
      }
    };
    window.addEventListener('keydown', onKeyDown);

    return () => {
      for (const [action] of bindings) store.unregisterHandler(action);
      removeListener?.();
      window.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  const nodeTypes = useMemo(
    () => ({
      workflow: TypedNodeView,
      [CANVAS_ASSET_NODE_TYPE]: CanvasAssetNodeView,
      reroute: RerouteNodeView,
      group: GroupNodeView,
    }),
    [],
  );
  const edgeTypes = useMemo(() => ({ workflow: WorkflowEdge }), []);

  const selectedNodes = nodes.filter((n) => n.selected);
  const selectedNode =
    selectedNodes.length === 1 && selectedNodes[0]!.type === 'workflow'
      ? selectedNodes[0]
      : undefined;
  const selectedWorkflowCount = selectedNodes.filter((n) => n.type === 'workflow').length;
  const hasSelectedGroup = selectedNodes.some((n) => n.type === 'group');

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
          <button
            className={cn(
              'rounded p-1.5 text-muted-foreground hover:bg-accent',
              rightPanel && 'bg-accent text-foreground',
            )}
            onClick={() => setRightPanel((p) => (p ? null : 'run'))}
            title={t('flowEditor.toggleRunPanel', 'Toggle run panel')}
          >
            <PanelRight className="h-4 w-4" />
          </button>
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
          onDragOver={onDragOverCanvas}
          onDragLeave={onDragLeaveCanvas}
          onDoubleClick={(e) => {
            const target = e.target as HTMLElement;
            if (target.classList.contains('react-flow__pane')) {
              setPaletteAt({ x: e.clientX, y: e.clientY });
            }
          }}
        >
          {canvasDragActive && (
            <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center border-2 border-dashed border-primary/60 bg-primary/5">
              <p className="rounded-lg bg-surface-elevated/90 px-4 py-2 text-sm font-medium text-foreground shadow-lg">
                {t('flowEditor.dropAssetHint', '拖放图片、文本或文件到画布')}
              </p>
            </div>
          )}
          {assetDropBusy && (
            <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center bg-background/40">
              <p className="text-sm text-muted-foreground">{t('flowEditor.uploadingAsset', '上传中…')}</p>
            </div>
          )}
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onConnectStart={onConnectStart}
            onConnectEnd={onConnectEnd}
            onEdgeDoubleClick={onEdgeDoubleClick}
            onNodeDoubleClick={onNodeDoubleClick}
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
            {(selectedWorkflowCount >= 2 || hasSelectedGroup) && (
              <Panel position="top-center">
                <div className="flex items-center gap-0.5 rounded-lg border border-border bg-surface px-1 py-0.5 shadow-md">
                  {selectedWorkflowCount >= 2 && (
                    <>
                      {(
                        [
                          ['left', AlignStartVertical, t('flowEditor.alignLeft', 'Align left')],
                          ['centerX', AlignCenterVertical, t('flowEditor.alignCenterX', 'Align horizontal centers')],
                          ['right', AlignEndVertical, t('flowEditor.alignRight', 'Align right')],
                          ['top', AlignStartHorizontal, t('flowEditor.alignTop', 'Align top')],
                          ['centerY', AlignCenterHorizontal, t('flowEditor.alignCenterY', 'Align vertical centers')],
                          ['bottom', AlignEndHorizontal, t('flowEditor.alignBottom', 'Align bottom')],
                        ] as const
                      ).map(([mode, Icon, label]) => (
                        <button
                          key={mode}
                          className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                          onClick={() => alignSelection(mode)}
                          title={label}
                        >
                          <Icon className="h-3.5 w-3.5" />
                        </button>
                      ))}
                      {selectedWorkflowCount >= 3 && (
                        <>
                          <button
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                            onClick={() => distributeSelection('x')}
                            title={t('flowEditor.distributeH', 'Distribute horizontally')}
                          >
                            <AlignHorizontalDistributeCenter className="h-3.5 w-3.5" />
                          </button>
                          <button
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                            onClick={() => distributeSelection('y')}
                            title={t('flowEditor.distributeV', 'Distribute vertically')}
                          >
                            <AlignVerticalDistributeCenter className="h-3.5 w-3.5" />
                          </button>
                        </>
                      )}
                      <span className="mx-0.5 h-4 w-px bg-border" />
                      <button
                        className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                        onClick={groupSelection}
                        title={t('flowEditor.groupSelection', 'Group selection')}
                      >
                        <Group className="h-3.5 w-3.5" />
                      </button>
                      <button
                        className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                        onClick={() => void extractSubworkflow()}
                        title={t('flowEditor.extractSubgraph', 'Convert to subworkflow')}
                      >
                        <Combine className="h-3.5 w-3.5" />
                      </button>
                    </>
                  )}
                  {hasSelectedGroup && (
                    <button
                      className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                      onClick={ungroupSelection}
                      title={t('flowEditor.ungroup', 'Ungroup')}
                    >
                      <Ungroup className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </Panel>
            )}
            <Panel position="bottom-center">
              <span className="rounded bg-surface/80 px-2 py-1 text-[10px] text-muted-foreground">
                {t('flowEditor.paletteHint', 'Double-click canvas to search nodes')}
              </span>
            </Panel>
          </ReactFlow>

          {paletteAt && (
            <NodeSearchPalette
              registry={registry}
              typeFilter={
                paletteLink
                  ? ({
                      type: paletteLink.type,
                      direction: paletteLink.handleType === 'source' ? 'out' : 'in',
                    } satisfies PaletteTypeFilter)
                  : null
              }
              onClose={() => {
                setPaletteAt(null);
                setPaletteLink(null);
              }}
              onSelect={(def) => {
                const newNodeId = addNode(def, rf.screenToFlowPosition(paletteAt));
                if (paletteLink) {
                  // Auto-connect the dangling link to the first compatible slot.
                  const link = paletteLink;
                  if (link.handleType === 'source') {
                    const slot = def.inputs.find((s) => typesCompatible(link.type, s.type));
                    if (slot) {
                      onConnect({
                        source: link.nodeId,
                        sourceHandle: link.handleId,
                        target: newNodeId,
                        targetHandle: slot.id,
                      });
                    }
                  } else {
                    const slot = def.outputs.find((s) => typesCompatible(s.type, link.type));
                    if (slot) {
                      onConnect({
                        source: newNodeId,
                        sourceHandle: slot.id,
                        target: link.nodeId,
                        targetHandle: link.handleId,
                      });
                    }
                  }
                }
                setPaletteAt(null);
                setPaletteLink(null);
              }}
            />
          )}

          {/* Floating fallback; the Run panel hosts the GenUI pause/review form. */}
          {!rightPanel && <ResumePanel />}
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

        {rightPanel && (
          <aside className="flex w-96 shrink-0 flex-col border-l border-border bg-surface">
            <div className="flex items-center gap-1 border-b border-border px-2 py-1.5">
              {(['run', 'io'] as const).map((tab) => (
                <button
                  key={tab}
                  className={cn(
                    'rounded px-2.5 py-1 text-xs font-medium transition-colors',
                    rightPanel === tab
                      ? 'bg-accent text-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                  onClick={() => setRightPanel(tab)}
                >
                  {tab === 'run'
                    ? t('runPanel.tab', 'Run')
                    : t('ioPanel.tab', 'Inputs / Outputs')}
                </button>
              ))}
            </div>
            {rightPanel === 'run' ? (
              <WorkflowRunPanel
                flowId={flowId}
                inputs={docInputs}
                outputs={docOutputs}
                onBeforeRun={async () => {
                  await handleSave();
                }}
                className="flex-1"
              />
            ) : (
              <WorkflowIOPanel
                inputs={docInputs}
                outputs={docOutputs}
                onChangeInputs={setDocInputs}
                onChangeOutputs={setDocOutputs}
              />
            )}
          </aside>
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
  const { t } = useTranslation();
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
