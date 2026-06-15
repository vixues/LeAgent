import { useEffect, useRef } from 'react';
import { useExecutionOverlay } from '@/features/workflow/store/executionOverlay';
import { useChatStore } from '@/stores/chat';
import { syncSessionTodosFromWorkflow } from './workflowTodoSync';

/**
 * Syncs terminal execution overlay state back into chat workflow step runs.
 * Covers late WebSocket completion and future async step execution paths.
 */
export function useWorkflowStepOverlaySync(sessionId: string, messageId: string) {
  const updateStep = useChatStore((s) => s.updateWorkflowStepRun);
  const prevRunningRef = useRef<Record<string, boolean>>({});

  useEffect(() => {
    const unsubscribe = useExecutionOverlay.subscribe((state) => {
      const message = useChatStore
        .getState()
        .messages[sessionId]?.find((m) => m.id === messageId);
      const stepRuns = message?.workflow?.stepRuns;
      if (!stepRuns) return;

      for (const [stepId, run] of Object.entries(stepRuns)) {
        const promptId = run.prompt_id;
        if (!promptId) continue;
        if (run.status === 'success' || run.status === 'error') continue;

        const overlay = state.overlays[promptId];
        if (!overlay) continue;

        const wasRunning = prevRunningRef.current[promptId] ?? overlay.running;
        const isRunning = overlay.running;
        prevRunningRef.current[promptId] = isRunning;

        if (!wasRunning || isRunning || overlay.blocked) continue;

        if (overlay.errors.length > 0) {
          updateStep(sessionId, messageId, stepId, {
            status: 'error',
            error: overlay.errors.join('; '),
          });
        } else if (run.status === 'running') {
          updateStep(sessionId, messageId, stepId, { status: 'success' });
        }

        const wf = useChatStore.getState().messages[sessionId]?.find((m) => m.id === messageId)
          ?.workflow;
        if (wf) {
          syncSessionTodosFromWorkflow(sessionId, wf.spec.steps, wf.stepRuns);
        }
      }
    });

    return unsubscribe;
  }, [sessionId, messageId, updateStep]);
}
