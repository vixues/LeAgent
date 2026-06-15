import { useExecutionOverlay } from '@/features/workflow/store/executionOverlay';
import { useChatStore } from '@/stores/chat';
import type {
  ChatWorkflowStepModel,
  ChatWorkflowStepRunRecord,
  TaskProgressStep,
} from '@/types/chat';

const STATUS_RANK: Record<TaskProgressStep['status'], number> = {
  pending: 0,
  in_progress: 1,
  completed: 2,
  failed: 2,
  cancelled: 2,
};

type OverlayLookup = (promptId: string) =>
  | { running: boolean; blocked: unknown; errors: string[] }
  | undefined;

function defaultOverlayLookup(promptId: string) {
  return useExecutionOverlay.getState().overlays[promptId];
}

/** Mirror ChatWorkflowStepRail terminal/running resolution for todo rows. */
export function resolveWorkflowRunTodoStatus(
  run: ChatWorkflowStepRunRecord | undefined,
  getOverlay: OverlayLookup = defaultOverlayLookup,
): TaskProgressStep['status'] | null {
  if (!run || run.status === 'idle') return null;

  const promptId = run.prompt_id;
  const overlay = promptId ? getOverlay(promptId) : undefined;
  const liveRunning = Boolean(promptId && overlay?.running);
  const liveBlocked = Boolean(overlay?.blocked);
  const overlayTerminal = Boolean(promptId) && !liveRunning && !liveBlocked;
  const overlayErrorCount = overlay?.errors.length ?? 0;
  const staleRunning =
    run.status === 'running' && Boolean(promptId) && overlayTerminal && overlayErrorCount === 0;

  if (run.status === 'error' || (overlayTerminal && overlayErrorCount > 0)) {
    return 'failed';
  }
  if (
    run.status === 'success' ||
    staleRunning ||
    (run.status === 'running' && overlayTerminal && overlayErrorCount === 0)
  ) {
    return 'completed';
  }
  if (run.status === 'running' || liveRunning || liveBlocked) {
    return 'in_progress';
  }
  return null;
}

function workflowRunStatusToTodoStatus(
  run: ChatWorkflowStepRunRecord | undefined,
  getOverlay?: OverlayLookup,
): TaskProgressStep['status'] | null {
  return resolveWorkflowRunTodoStatus(run, getOverlay);
}

function resolveStepForTodo(
  steps: ChatWorkflowStepModel[],
  todo: TaskProgressStep,
  index: number,
): ChatWorkflowStepModel | undefined {
  return steps.find((s) => s.id === todo.taskId) ?? steps[index];
}

/** Overlay-aware workflow step run state onto parallel session todo rows (by step id or index). */
export function mergeWorkflowIntoTodos(
  steps: ChatWorkflowStepModel[],
  stepRuns: Record<string, ChatWorkflowStepRunRecord>,
  todos: TaskProgressStep[],
  getOverlay?: OverlayLookup,
): TaskProgressStep[] {
  if (!steps.length || !todos.length) return todos;

  return todos.map((todo, index) => {
    const step = resolveStepForTodo(steps, todo, index);
    if (!step) return todo;
    const mapped = workflowRunStatusToTodoStatus(stepRuns[step.id], getOverlay);
    if (!mapped) return todo;
    if (STATUS_RANK[mapped] >= STATUS_RANK[todo.status]) {
      return { ...todo, status: mapped };
    }
    return todo;
  });
}

function findLatestTodoAnchorMessageId(sessionId: string): string | null {
  const messages = useChatStore.getState().messages[sessionId] ?? [];
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (!m || m.role !== 'assistant') continue;
    if (m.taskProgress?.length) return m.id;
    if (m.toolCalls?.some((tc) =>
      ['todo_write', 'todo', 'todo_create', 'update_todo', 'create_todo'].includes(tc.name),
    )) {
      return m.id;
    }
  }
  return null;
}

/** Push merged workflow/todo state into session todos + anchor message taskProgress. */
export function syncSessionTodosFromWorkflow(
  sessionId: string,
  steps: ChatWorkflowStepModel[],
  stepRuns: Record<string, ChatWorkflowStepRunRecord>,
): void {
  const state = useChatStore.getState();
  const sessionTodos = state.sessions.find((s) => s.id === sessionId)?.todos ?? [];
  const anchorId = findLatestTodoAnchorMessageId(sessionId);
  const anchorTodos =
    anchorId != null
      ? (state.messages[sessionId]?.find((m) => m.id === anchorId)?.taskProgress ?? [])
      : [];
  const baseline = sessionTodos.length > 0 ? sessionTodos : anchorTodos;
  if (!baseline.length) return;

  const merged = mergeWorkflowIntoTodos(steps, stepRuns, baseline);
  const unchanged =
    merged.length === baseline.length &&
    merged.every(
      (item, i) =>
        item.taskId === baseline[i]?.taskId &&
        item.status === baseline[i]?.status &&
        item.label === baseline[i]?.label,
    );
  if (unchanged) return;

  useChatStore.getState().setSessionTodos(sessionId, merged);

  if (!anchorId) return;
  useChatStore.setState((s) => ({
    messages: {
      ...s.messages,
      [sessionId]: (s.messages[sessionId] || []).map((m) =>
        m.id === anchorId ? { ...m, taskProgress: merged } : m,
      ),
    },
  }));
}
