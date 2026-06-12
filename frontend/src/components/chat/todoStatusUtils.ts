import type { TaskProgressStatus } from '@/types/chat';

/** Cursor-style click cycle: pending → in_progress → completed → pending. */
export function nextTodoStatusOnClick(status: TaskProgressStatus): TaskProgressStatus {
  switch (status) {
    case 'pending':
      return 'in_progress';
    case 'in_progress':
      return 'completed';
    case 'completed':
      return 'pending';
    case 'cancelled':
    case 'failed':
      return 'pending';
    default:
      return 'pending';
  }
}

export function todoStatusI18nKey(status: TaskProgressStatus): string {
  switch (status) {
    case 'in_progress':
      return 'chat.sessionTodos.statusInProgress';
    case 'completed':
      return 'chat.sessionTodos.statusCompleted';
    case 'cancelled':
      return 'chat.sessionTodos.statusCancelled';
    case 'failed':
      return 'chat.sessionTodos.statusFailed';
    default:
      return 'chat.sessionTodos.statusPending';
  }
}
