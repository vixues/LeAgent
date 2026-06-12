import { useCallback } from 'react';
import type { TFunction } from 'i18next';
import { apiClient } from '@/api/client';
import { resumeChatCheckpoint } from '@/hooks/useCheckpointResume';

export type ExecutionResumeScope = 'chat_turn' | 'workflow';

export interface ExecutionResumeRequest {
  scope: ExecutionResumeScope;
  sessionId?: string;
  promptId?: string;
  checkpointId?: string;
  answer?: string;
  prompt?: string;
}

async function resumeWorkflowPrompt(request: ExecutionResumeRequest): Promise<void> {
  if (!request.promptId) return;
  await apiClient.post(`/workflow/prompts/${request.promptId}/resume`, {
    answer: request.answer ?? request.prompt ?? '',
    checkpoint_id: request.checkpointId,
  });
}

/** Workflow-only resume (no i18n required). */
export async function resumeWorkflowExecution(
  request: Pick<ExecutionResumeRequest, 'promptId' | 'checkpointId' | 'answer' | 'prompt'> & {
    promptId: string;
  },
): Promise<void> {
  await resumeWorkflowPrompt({ scope: 'workflow', ...request });
}

/**
 * Standalone resume helper (usable outside React hooks).
 * Chat-turn resumes require a `TFunction` for error strings and stream handling.
 */
export async function resumeExecution(
  request: ExecutionResumeRequest,
  t: TFunction,
): Promise<void> {
  if (request.scope === 'chat_turn') {
    if (!request.sessionId) return;
    await resumeChatCheckpoint(
      request.sessionId,
      request.prompt ?? request.answer ?? '',
      t,
    );
    return;
  }
  await resumeWorkflowPrompt(request);
}

/**
 * Unified pause/resume hook for chat agent checkpoints and workflow prompt resumes.
 */
export function useExecutionResume(t: TFunction) {
  return useCallback(
    async (request: ExecutionResumeRequest) => {
      await resumeExecution(request, t);
    },
    [t],
  );
}
