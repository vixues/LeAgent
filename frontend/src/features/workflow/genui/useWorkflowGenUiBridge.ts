/**
 * Bridges GenUI `run_workflow` / `resume_workflow` actions onto the workflow
 * HTTP API while the host surface (editor Run panel, Playground) is mounted.
 *
 * The started run is tracked in `useExecutionOverlay` so the surface's
 * `useExecutionStream(promptId)` picks up the live event stream.
 */

import { useEffect, useRef } from 'react';

import { apiClient } from '@/api/client';
import {
  registerGenUiActionAdapters,
  type ResumeWorkflowActionPayload,
  type RunWorkflowActionPayload,
} from '@/lib/genUiActionBus';
import { resumeWorkflowExecution } from '@/hooks/useExecutionResume';

import { useExecutionOverlay } from '../store/executionOverlay';
import { coerceFormValues, missingRequiredInputs, type WorkflowInputSpec } from './inputsToGenUiTree';
import { collectWorkflowRunInputValues } from './workflowRunForm';

interface RunResponse {
  execution_id: string;
  prompt_id: string;
  flow_id: string;
  status: string;
}

export interface WorkflowGenUiBridgeOptions {
  /** Declared input specs, used to coerce string form values back to types. */
  inputs?: WorkflowInputSpec[] | null;
  /** Invoked before the run request (e.g. editor saves the draft first). */
  onBeforeRun?: (p: RunWorkflowActionPayload) => Promise<void> | void;
  onRunStarted?: (res: RunResponse) => void;
  onResumed?: (promptId: string) => void;
  onError?: (message: string) => void;
}

export function useWorkflowGenUiBridge(opts: WorkflowGenUiBridgeOptions = {}): void {
  // Keep latest options without re-registering adapters on each render.
  const optsRef = useRef(opts);
  optsRef.current = opts;

  useEffect(() => {
    registerGenUiActionAdapters({
      async runWorkflow(p: RunWorkflowActionPayload) {
        const o = optsRef.current;
        try {
          await o.onBeforeRun?.(p);
          const merged =
            p.values && Object.keys(p.values).length > 0
              ? coerceFormValues(p.values, o.inputs)
              : collectWorkflowRunInputValues(p.flowId, o.inputs);
          const missing = missingRequiredInputs(merged, o.inputs);
          if (missing.length > 0) {
            o.onError?.(`Missing required inputs: ${missing.join(', ')}`);
            return;
          }
          const res = await apiClient.post<RunResponse>(`/workflow/flows/${p.flowId}/run`, {
            input_data: merged,
            priority: 5,
            trigger_type: 'manual',
          });
          useExecutionOverlay.getState().start(res.prompt_id);
          o.onRunStarted?.(res);
        } catch (err) {
          o.onError?.(err instanceof Error ? err.message : 'Run failed');
        }
      },
      async resumeWorkflow(p: ResumeWorkflowActionPayload) {
        const o = optsRef.current;
        try {
          await resumeWorkflowExecution({
            promptId: p.promptId,
            answer: typeof p.values?.answer === 'string' ? p.values.answer : undefined,
            prompt: typeof p.values?.prompt === 'string' ? p.values.prompt : undefined,
            checkpointId:
              typeof p.values?.checkpoint_id === 'string' ? p.values.checkpoint_id : undefined,
          });
          useExecutionOverlay.getState().setBlocked(p.promptId, null);
          o.onResumed?.(p.promptId);
        } catch (err) {
          o.onError?.(err instanceof Error ? err.message : 'Resume failed');
        }
      },
    });
  }, []);
}
