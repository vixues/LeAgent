import { useCallback } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { cn } from '@/lib/utils';
import { isChatStreamBusyForSession, useChatStore } from '@/stores/chat';
import type { TaskProgressStep } from '@/types/chat';
import { TodoListBlock } from './TodoListBlock';

interface SessionTodoPanelProps {
  sessionId: string | null | undefined;
  className?: string;
}

const EMPTY_TODOS: TaskProgressStep[] = [];

/** Sticky todo panel at the top of the chat page (when pinned and not dismissed). */
export function SessionTodoPanel({ sessionId, className }: SessionTodoPanelProps) {
  const todos = useChatStore(
    useShallow((state) => {
      if (!sessionId) return EMPTY_TODOS;
      return state.sessions.find((s) => s.id === sessionId)?.todos ?? EMPTY_TODOS;
    }),
  );

  const ui = useChatStore((state) =>
    sessionId ? state.sessionTodoUi[sessionId] : undefined,
  );

  const isStreaming = useChatStore((state) =>
    sessionId ? isChatStreamBusyForSession(sessionId, state) : false,
  );

  const setSessionTodoPinned = useChatStore((s) => s.setSessionTodoPinned);
  const dismissSessionTodoPanel = useChatStore((s) => s.dismissSessionTodoPanel);
  const patchSessionTodoStatus = useChatStore((s) => s.patchSessionTodoStatus);

  const handleStatusChange = useCallback(
    (taskId: string, status: TaskProgressStep['status']) => {
      if (!sessionId) return Promise.resolve();
      return patchSessionTodoStatus(sessionId, taskId, status);
    },
    [patchSessionTodoStatus, sessionId],
  );

  if (!sessionId || !ui?.pinned || ui.dismissed || todos.length === 0) {
    return null;
  }

  return (
    <div className={cn('chat-todo-panel-row', className)}>
      <div className="chat-composer-inner min-w-0">
        <TodoListBlock
          steps={todos}
          isStreaming={isStreaming}
          variant="pinned"
          interactive
          sessionId={sessionId}
          onStatusChange={handleStatusChange}
          showUnpin
          showClose
          onUnpin={() => setSessionTodoPinned(sessionId, false)}
          onClose={() => dismissSessionTodoPanel(sessionId)}
        />
      </div>
    </div>
  );
}
