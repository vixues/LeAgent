import { useEffect, useRef } from 'react';

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
  // base may be absolute or relative; resolve against the current origin.
  const url = new URL(path, window.location.origin);
  url.protocol = proto;
  return url.toString();
}

/**
 * Subscribe to the per-prompt execution WebSocket and drive the execution
 * overlay store (node highlighting + agent previews). Pass `null` to stop.
 */
export function useExecutionStream(promptId: string | null): void {
  const { start, setNode, setBlocked, addGenUiTree, finish } = useExecutionOverlay();
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!promptId) return;
    start(promptId);

    let closed = false;
    const socket = new WebSocket(wsUrl(promptId));
    socketRef.current = socket;

    socket.onmessage = (event) => {
      let msg: WsMessage;
      try {
        msg = JSON.parse(event.data as string);
      } catch {
        return;
      }
      const nodeId = msg.node_id ?? msg.state?.node_id;
      if (nodeId && msg.state) {
        const status = STATUS_MAP[msg.state.status ?? ''] ?? undefined;
        const max = msg.state.max || 1;
        setNode(nodeId, {
          ...(status ? { status } : {}),
          progress: msg.state.value != null ? msg.state.value / max : undefined,
          preview: msg.state.preview ?? undefined,
          error: msg.state.error ?? undefined,
        });
      } else if (nodeId && msg.type === 'executed') {
        setNode(nodeId, { status: 'success' });
      }
      if (nodeId && msg.type === 'executed') {
        // Nodes may publish ad-hoc GenUI trees via NodeOutput.ui.gen_ui.
        const ui = (msg.data?.ui ?? null) as Record<string, unknown> | null;
        const tree = ui ? asGenUiTree(ui.gen_ui) : null;
        if (tree) addGenUiTree(tree);
      }
      if (msg.type === 'execution_blocked' && nodeId) {
        const ui = (msg.data?.ui ?? {}) as Record<string, unknown>;
        setNode(nodeId, { status: 'blocked' });
        setBlocked({
          nodeId,
          tag: String(msg.data?.tag ?? ''),
          question: typeof ui.question === 'string' ? ui.question : undefined,
          checkpointId:
            typeof ui.checkpoint_id === 'string' ? ui.checkpoint_id : undefined,
          ui,
        });
        finish();
      } else if (msg.type === 'execution_start') {
        // A resumed run reuses the same prompt channel; restart the overlay.
        start(msg.prompt_id);
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
        finish({ outputs, errors });
        if (!closed) socket.close();
      }
    };

    socket.onerror = () => finish();
    socket.onclose = () => {
      closed = true;
    };

    return () => {
      closed = true;
      finish();
      socket.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [promptId]);
}
