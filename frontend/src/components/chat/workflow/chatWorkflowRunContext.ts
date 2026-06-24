import { createContext, useContext } from 'react';

/**
 * Active execution ``prompt_id`` for an in-chat workflow run, or ``null`` when
 * the embed has not been run. Provided around the chat mini-graph so each
 * {@link ChatWorkflowMiniNode} can read its live status from the execution
 * overlay without prop-drilling through ReactFlow node data.
 */
export const ChatWorkflowRunPromptContext = createContext<string | null>(null);

export function useChatWorkflowRunPromptId(): string | null {
  return useContext(ChatWorkflowRunPromptContext);
}
