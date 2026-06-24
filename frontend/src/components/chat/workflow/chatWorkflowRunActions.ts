/**
 * Store-driven run actions for chat workflow cards, decoupled from React so
 * they can be invoked from hooks (card chrome) and from the singleton GenUI
 * action bus (`run_workflow` dispatched by a generated input form).
 *
 * Both the DAG embed and per-step paths go through the verified chat HTTP
 * endpoints (digest checked server-side) and drive the shared execution
 * overlay so the chat mini-graph / step rail render live per-node status.
 */

import { apiClient } from '@/api/client';
import { useExecutionOverlay } from '@/features/workflow/store/executionOverlay';
import { useChatStore } from '@/stores/chat';
import { useExecutionSessionStore } from '@/stores/executionSession';

import { syncSessionTodosFromWorkflow } from './workflowTodoSync';

interface StartEmbedResult {
  success: boolean;
  status?: string | null;
  error?: string | null;
  prompt_id?: string | null;
  run_id?: string | null;
}

interface RunStepResult {
  success: boolean;
  data?: unknown;
  error?: string | null;
  prompt_id?: string | null;
  run_id?: string | null;
}

export interface StartChatEmbedRunArgs {
  sessionId: string;
  messageId: string;
  digest: string;
  /** Structured input values from the generated GenUI form. */
  inputs?: Record<string, unknown>;
  /** Legacy single placeholder value (kept for back-compat). */
  userInput?: string;
  /** Localized fallback error message. */
  fallbackError?: string;
}

/** Start a whole DAG embed run in the background via the verified endpoint. */
export async function startChatWorkflowEmbedRun(args: StartChatEmbedRunArgs): Promise<void> {
  const { sessionId, messageId, digest, inputs, userInput, fallbackError = 'Run failed' } = args;
  const chat = useChatStore.getState();
  chat.updateWorkflowEmbedRun(sessionId, messageId, {
    status: 'running',
    error: undefined,
    promptId: undefined,
  });
  const parentRunId =
    useExecutionSessionStore.getState().bySession[sessionId]?.runId ?? undefined;
  try {
    const hasInputs = Boolean(inputs && Object.keys(inputs).length > 0);
    const res = await apiClient.post<StartEmbedResult>(
      `/chat/sessions/${sessionId}/workflow-embeds/${encodeURIComponent(messageId)}/run`,
      {
        message_id: messageId,
        workflow_digest: digest,
        user_input: userInput?.trim() ?? '',
        inputs: hasInputs ? inputs : undefined,
        parent_run_id: parentRunId,
      },
    );
    if (!res.success || !res.prompt_id) {
      chat.updateWorkflowEmbedRun(sessionId, messageId, {
        status: 'error',
        error: res.error || fallbackError,
      });
      return;
    }
    const promptId = res.prompt_id;
    useExecutionOverlay.getState().start(promptId, 'chat');
    useExecutionSessionStore.getState().upsertFromStarted(sessionId, {
      runId: res.run_id ?? promptId,
      scope: 'workflow',
      promptId,
      parentRunId,
    });
    chat.updateWorkflowEmbedRun(sessionId, messageId, {
      status: 'running',
      promptId,
      runId: res.run_id ?? undefined,
    });
  } catch (e) {
    chat.updateWorkflowEmbedRun(sessionId, messageId, {
      status: 'error',
      error: e instanceof Error ? e.message : fallbackError,
    });
  }
}

export interface RunChatStepArgs {
  sessionId: string;
  messageId: string;
  stepId: string;
  digest: string;
  userInput?: string;
  fallbackError?: string;
}

/** Execute a single persisted chat workflow step via the verified endpoint. */
export async function runChatWorkflowStep(args: RunChatStepArgs): Promise<void> {
  const { sessionId, messageId, stepId, digest, userInput, fallbackError = 'Step failed' } = args;
  const chat = useChatStore.getState();
  chat.updateWorkflowStepRun(sessionId, messageId, stepId, { status: 'running', error: undefined });

  const syncTodos = () => {
    const wf = useChatStore.getState().messages[sessionId]?.find((m) => m.id === messageId)
      ?.workflow;
    if (wf) syncSessionTodosFromWorkflow(sessionId, wf.spec.steps, wf.stepRuns);
  };
  syncTodos();

  const parentRunId =
    useExecutionSessionStore.getState().bySession[sessionId]?.runId ?? undefined;
  try {
    const res = await apiClient.post<RunStepResult>(
      `/chat/sessions/${sessionId}/workflow-steps/${encodeURIComponent(stepId)}/run`,
      {
        message_id: messageId,
        workflow_digest: digest,
        user_input: userInput?.trim() ?? '',
        parent_run_id: parentRunId,
      },
    );
    const promptId = res.prompt_id ?? undefined;
    const stepPatch = { prompt_id: promptId, run_id: res.run_id ?? undefined };
    if (promptId) {
      useExecutionSessionStore.getState().upsertFromStarted(sessionId, {
        runId: res.run_id ?? promptId,
        scope: 'workflow',
        promptId,
        parentRunId,
      });
    }
    if (!res.success) {
      chat.updateWorkflowStepRun(sessionId, messageId, stepId, {
        status: 'error',
        error: res.error || fallbackError,
        ...stepPatch,
      });
    } else {
      chat.updateWorkflowStepRun(sessionId, messageId, stepId, { status: 'success', ...stepPatch });
    }
  } catch (e) {
    chat.updateWorkflowStepRun(sessionId, messageId, stepId, {
      status: 'error',
      error: e instanceof Error ? e.message : fallbackError,
    });
  } finally {
    syncTodos();
  }
}
