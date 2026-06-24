import { useEffect, useRef } from 'react';
import { useExecutionOverlay } from '@/features/workflow/store/executionOverlay';
import { useChatStore } from '@/stores/chat';

/**
 * Reconciles terminal execution-overlay state back into a chat embed run.
 *
 * The embed runs in the background and streams per-node status over the
 * execution WebSocket. When the overlay for the run's ``promptId`` stops
 * running, flip the embed run to ``success``/``error`` (the backend persists
 * the authoritative terminal status to extensions in parallel).
 */
export function useWorkflowEmbedOverlaySync(sessionId: string, messageId: string) {
  const updateEmbedRun = useChatStore((s) => s.updateWorkflowEmbedRun);
  const prevRunningRef = useRef<Record<string, boolean>>({});

  useEffect(() => {
    const unsubscribe = useExecutionOverlay.subscribe((state) => {
      const message = useChatStore
        .getState()
        .messages[sessionId]?.find((m) => m.id === messageId);
      const run = message?.workflowEmbed?.run;
      const promptId = run?.promptId;
      if (!run || !promptId) return;
      if (run.status !== 'running') return;

      const overlay = state.overlays[promptId];
      if (!overlay) return;

      const wasRunning = prevRunningRef.current[promptId] ?? overlay.running;
      const isRunning = overlay.running;
      prevRunningRef.current[promptId] = isRunning;

      if (!wasRunning || isRunning || overlay.blocked) return;

      if (overlay.errors.length > 0) {
        updateEmbedRun(sessionId, messageId, {
          status: 'error',
          error: overlay.errors.join('; '),
        });
      } else {
        updateEmbedRun(sessionId, messageId, {
          status: 'success',
          outputs:
            overlay.outputs && typeof overlay.outputs === 'object'
              ? overlay.outputs
              : undefined,
        });
      }
    });

    return unsubscribe;
  }, [sessionId, messageId, updateEmbedRun]);
}
