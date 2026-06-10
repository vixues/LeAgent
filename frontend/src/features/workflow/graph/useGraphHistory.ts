/**
 * Snapshot-based undo/redo + clipboard for the graph editor (ComfyUI
 * `ChangeTracker` analogue). Graph changes are observed and coalesced with a
 * short debounce, so drags and rapid widget edits collapse into one entry.
 */

import { useCallback, useEffect, useRef } from 'react';

import type { EditorEdge, EditorNode } from './serialization';

interface Snapshot {
  nodes: EditorNode[];
  edges: EditorEdge[];
}

const MAX_HISTORY = 100;
const DEBOUNCE_MS = 250;
const PASTE_OFFSET = 28;

export interface GraphHistoryApi {
  undo: () => void;
  redo: () => void;
  copySelection: () => void;
  /** Paste the clipboard. `withConnect` keeps incoming links from nodes that
   * were not part of the copied set (ComfyUI paste-with-connect). */
  paste: (withConnect?: boolean) => void;
}

function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `n_${Math.random().toString(36).slice(2)}`;
}

export function useGraphHistory(params: {
  nodes: EditorNode[];
  edges: EditorEdge[];
  setNodes: (updater: EditorNode[] | ((cur: EditorNode[]) => EditorNode[])) => void;
  setEdges: (updater: EditorEdge[] | ((cur: EditorEdge[]) => EditorEdge[])) => void;
}): GraphHistoryApi {
  const { nodes, edges, setNodes, setEdges } = params;

  const past = useRef<Snapshot[]>([]);
  const future = useRef<Snapshot[]>([]);
  const current = useRef<Snapshot>({ nodes, edges });
  const applying = useRef(false);
  const clipboard = useRef<Snapshot | null>(null);
  // Live view of the graph (clipboard ops must not lag behind the debounce).
  const live = useRef<Snapshot>({ nodes, edges });
  live.current = { nodes, edges };

  // Observe graph changes; push coalesced snapshots onto the undo stack.
  useEffect(() => {
    if (applying.current) {
      applying.current = false;
      current.current = { nodes, edges };
      return;
    }
    if (current.current.nodes === nodes && current.current.edges === edges) return;
    const timer = setTimeout(() => {
      past.current.push(current.current);
      if (past.current.length > MAX_HISTORY) past.current.shift();
      future.current = [];
      current.current = { nodes, edges };
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [nodes, edges]);

  const apply = useCallback(
    (snap: Snapshot) => {
      applying.current = true;
      setNodes(snap.nodes);
      setEdges(snap.edges);
    },
    [setNodes, setEdges],
  );

  const undo = useCallback(() => {
    const prev = past.current.pop();
    if (!prev) return;
    future.current.push(current.current);
    apply(prev);
  }, [apply]);

  const redo = useCallback(() => {
    const next = future.current.pop();
    if (!next) return;
    past.current.push(current.current);
    apply(next);
  }, [apply]);

  const copySelection = useCallback(() => {
    const selected = live.current.nodes.filter((n) => n.selected);
    if (selected.length === 0) return;
    const ids = new Set(selected.map((n) => n.id));
    // Keep edges with a selected target; internal edges paste fully, external
    // sources are reconnected only in paste-with-connect mode.
    const relevant = live.current.edges.filter((e) => ids.has(e.target));
    clipboard.current = {
      nodes: structuredClone(selected),
      edges: structuredClone(relevant),
    };
  }, []);

  const paste = useCallback(
    (withConnect = false) => {
      const clip = clipboard.current;
      if (!clip || clip.nodes.length === 0) return;
      const idMap = new Map<string, string>();
      for (const node of clip.nodes) idMap.set(node.id, newId());

      const newNodes: EditorNode[] = clip.nodes.map((node) => ({
        ...structuredClone(node),
        id: idMap.get(node.id)!,
        position: {
          x: node.position.x + PASTE_OFFSET,
          y: node.position.y + PASTE_OFFSET,
        },
        selected: true,
      }));

      const newEdges: EditorEdge[] = [];
      for (const edge of clip.edges) {
        const target = idMap.get(edge.target);
        if (!target) continue;
        const internalSource = idMap.get(edge.source);
        const source = internalSource ?? (withConnect ? edge.source : null);
        if (!source) continue;
        if (!internalSource) {
          // External source must still exist in the live graph.
          const exists = live.current.nodes.some((n) => n.id === edge.source);
          if (!exists) continue;
        }
        newEdges.push({
          ...structuredClone(edge),
          id: `e-${source}-${edge.sourceHandle ?? '0'}-${target}-${edge.targetHandle ?? '0'}`,
          source,
          target,
          selected: false,
        });
      }

      setNodes((cur) => [...cur.map((n) => ({ ...n, selected: false })), ...newNodes]);
      if (newEdges.length > 0) setEdges((cur) => [...cur, ...newEdges]);
    },
    [setNodes, setEdges],
  );

  return { undo, redo, copySelection, paste };
}
