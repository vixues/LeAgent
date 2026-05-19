import { useMemo } from 'react';
import { useChatStore } from '@/stores/chat';
import { ChatPermissionRequestBar } from '@/components/chat/ChatPermissionRequestBar';
import { ChatUserInputRequestBar } from '@/components/chat/ChatUserInputRequestBar';

interface ChatComposerUserInputGateProps {
  onSubmitAnswers: (answers: Record<string, string | string[]>) => void | Promise<void>;
  className?: string;
}

/**
 * Renders the permission strip for single ``ask_user`` questions with
 * ``ui_variant: permission``; otherwise the generic questionnaire bar.
 */
export function ChatComposerUserInputGate({
  onSubmitAnswers,
  className,
}: ChatComposerUserInputGateProps) {
  const pending = useChatStore((s) => s.pendingUserInput);
  const currentSessionId = useChatStore((s) => s.currentSessionId);

  const usePermissionUi = useMemo(() => {
    if (!pending || !currentSessionId || pending.sessionId !== currentSessionId) return false;
    if (pending.questions.length !== 1) return false;
    const question = pending.questions[0];
    return question?.ui_variant === 'permission';
  }, [pending, currentSessionId]);

  if (usePermissionUi) {
    return (
      <ChatPermissionRequestBar onSubmitAnswers={onSubmitAnswers} className={className} />
    );
  }
  return (
    <ChatUserInputRequestBar onSubmitAnswers={onSubmitAnswers} className={className} />
  );
}
