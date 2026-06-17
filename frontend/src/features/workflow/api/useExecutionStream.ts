import { useEffect } from 'react';

import {
  useExecutionOverlay,
  type NodeRunStatus,
} from '../store/executionOverlay';
import type { GenUiTreeV1 } from '@/types/genUi';

interface WsState {
  node_id?: string;
  status?: string;
  value?: number;
  max?: number;
  preview?: unknown;
  error?: string | null;
}

interface WsMessage {
  type: string;
  prompt_id: string;
  node_id?: string | null;
  state?: WsState | null;
  data?: Record<string, unknown>;
}

const STATUS_MAP: Record<string, NodeRunStatus> = {
  pending: 'pending',
  running: 'running',
  success: 'success',
  error: 'error',
  blocked: 'blocked',
  cached: 'cached',
  skipped: 'skipped',
};

const refCounts = new Map<string, number>();
const sockets = new Map<string, WebSocket>();

function asGenUiTree(value: unknown): GenUiTreeV1 | null {
  if (
    value &&
    typeof value === 'object' &&
    (value as { schemaVersion?: string }).schemaVersion === '1' &&
    (value as { root?: unknown }).root
  ) {
    return value as GenUiTreeV1;
  }
  return null;
}

function wsUrl(promptId: string): string {
  const base = import.meta.env.VITE_API_BASE_URL || '/api/v1';
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const path = `${base}/workflow/ws/executions/${promptId}`;
  const url = new URL(path, window.location.origin);
  url.protocol = proto;
  return url.toString();
}

function handleWsMessage(promptId: string, raw: string): void {
  let msg: WsMessage;
  try {
    msg = JSON.parse(raw);
  } catch {
    return;
  }

  const { start, setNode, setBlocked, addGenUiTree, finish } = useExecutionOverlay.getState();
  const nodeId = msg.node_id ?? msg.state?.node_id;

  if (nodeId && msg.state) {
    const status = STATUS_MAP[msg.state.status ?? ''] ?? undefined;
    const max = msg.state.max || 1;
    setNode(promptId, nodeId, {
      ...(status ? { status } : {}),
      progress: msg.state.value != null ? msg.state.value / max : undefined,
      preview: msg.state.preview ?? undefined,
      error: msg.state.error ?? undefined,
    });
  } else if (nodeId && msg.type === 'executed') {
    setNode(promptId, nodeId, { status: 'success' });
  }

  if (nodeId && msg.type === 'executed') {
    const ui = (msg.data?.ui ?? null) as Record<string, unknown> | null;
    const tree = ui ? asGenUiTree(ui.gen_ui) : null;
    if (tree) {
      addGenUiTree(promptId, tree);
      // Also pin it to the node so the canvas card renders an inline thumbnail.
      setNode(promptId, nodeId, { ui: tree });
    }
  }

  if (msg.type === 'execution_blocked' && nodeId) {
    const ui = (msg.data?.ui ?? {}) as Record<string, unknown>;
    setNode(promptId, nodeId, { status: 'blocked' });
    setBlocked(promptId, {
      nodeId,
      tag: String(msg.data?.tag ?? ''),
      question: typeof ui.question === 'string' ? ui.question : undefined,
      checkpointId: typeof ui.checkpoint_id === 'string' ? ui.checkpoint_id : undefined,
      ui,
    });
    finish(promptId);
  } else if (msg.type === 'execution_start') {
    const pid = msg.prompt_id || promptId;
    const { editorActivePromptId } = useExecutionOverlay.getState();
    const surface = editorActivePromptId === pid ? 'editor' : 'chat';
    start(pid, surface);
  }

  if (
    msg.type === 'execution_success' ||
    msg.type === 'execution_failed' ||
    msg.type === 'execution_cancelled'
  ) {
    const outputs =
      msg.data?.outputs && typeof msg.data.outputs === 'object'
        ? (msg.data.outputs as Record<string, unknown>)
        : undefined;
    const errors = Array.isArray(msg.data?.errors)
      ? (msg.data.errors as string[]).map(String)
      : undefined;
    finish(promptId, { outputs, errors });
    const socket = sockets.get(promptId);
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.close();
    }
  }
}

function connectPromptStream(promptId: string): void {
  let closed = false;
  const socket = new WebSocket(wsUrl(promptId));
  sockets.set(promptId, socket);

  socket.onmessage = (event) => {
    handleWsMessage(promptId, event.data as string);
  };

  socket.onerror = () => {
    /* Keep overlay state; terminal events or explicit finish drive completion. */
  };

  socket.onclose = () => {
    closed = true;
    sockets.delete(promptId);
  };

  socket.onopen = () => {
    if (closed) socket.close();
  };
}

function acquirePromptStream(promptId: string): void {
  const next = (refCounts.get(promptId) ?? 0) + 1;
  refCounts.set(promptId, next);
  if (next === 1) {
    connectPromptStream(promptId);
  }
}

function releasePromptStream(promptId: string): void {
  const prev = refCounts.get(promptId) ?? 0;
  if (prev <= 1) {
    refCounts.delete(promptId);
    const socket = sockets.get(promptId);
    if (socket) {
      socket.close();
      sockets.delete(promptId);
    }
  } else {
    refCounts.set(promptId, prev - 1);
  }
}

/** Test helper — reset module-level ref-counted sockets. */
export function resetExecutionStreamSubscriptions(): void {
  for (const socket of sockets.values()) {
    socket.close();
  }
  sockets.clear();
  refCounts.clear();
}

/**
 * Subscribe to the per-prompt execution WebSocket and drive the execution
 * overlay store (node highlighting + agent previews). Pass `null` to stop.
 * Multiple subscribers share one socket via ref-counting.
 */
export function useExecutionStream(promptId: string | null): void {
  useEffect(() => {
    if (!promptId) return;
    acquirePromptStream(promptId);
    return () => {
      releasePromptStream(promptId);
    };
  }, [promptId]);
}
