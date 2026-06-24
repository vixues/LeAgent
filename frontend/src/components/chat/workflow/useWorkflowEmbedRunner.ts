import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { startChatWorkflowEmbedRun } from './chatWorkflowRunActions';

/**
 * Starts a persisted chat workflow DAG embed (whole graph) via the verified
 * HTTP endpoint. The graph runs in the background; this drives the execution
 * overlay (surface 'chat') so the chat mini-graph renders live per-node status
 * from the execution WebSocket. The terminal run status is reconciled from the
 * overlay by {@link useWorkflowEmbedOverlaySync}.
 *
 * Accepts structured ``inputs`` (from the generated GenUI input form) and keeps
 * the legacy single ``userInput`` placeholder for back-compat.
 */
export function useWorkflowEmbedRunner(sessionId: string) {
  const { t } = useTranslation();

  const runEmbed = useCallback(
    async (
      messageId: string,
      workflowDigest: string,
      userInput?: string,
      inputs?: Record<string, unknown>,
    ) => {
      await startChatWorkflowEmbedRun({
        sessionId,
        messageId,
        digest: workflowDigest,
        inputs,
        userInput,
        fallbackError: t('chat.workflow.runFailed'),
      });
    },
    [sessionId, t],
  );

  return { runEmbed };
}
