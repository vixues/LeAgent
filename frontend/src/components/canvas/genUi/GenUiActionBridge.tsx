import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { isChatStreamBusyForSession, useChatStore } from '@/stores/chat';
import { useArtifactStore } from '@/stores/artifact';
import { useGenUiStore } from '@/stores/genUi';
import { getComposerModelMode } from '@/stores/chatDraft';
import { generateId } from '@/lib/utils';
import { handleChatStreamFailure, runChatStream } from '@/lib/runChatStream';
import { registerGenUiActionAdapters } from '@/lib/genUiActionBus';
import { apiClient } from '@/api/client';
import { resumeWorkflowExecution } from '@/hooks/useExecutionResume';
import { useExecutionOverlay } from '@/features/workflow/store/executionOverlay';
import { useExecutionSessionStore } from '@/stores/executionSession';
import type { Message } from '@/types/chat';

interface WorkflowRunResponse {
  execution_id: string;
  prompt_id: string;
  flow_id: string;
  status: string;
}

/**
 * Mounts once near the chat root and wires the singleton GenUi action bus to
 * the actual chat / artifact / router stores. This keeps `GenUiRegistry`
 * import-free of stores and routing — the registry only knows the bus API.
 */
export function GenUiActionBridge() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const navRef = useRef(navigate);
  const tRef = useRef(t);

  navRef.current = navigate;
  tRef.current = t;

  useEffect(() => {
    registerGenUiActionAdapters({
      async sendMessage(payload, ctx) {
        const content = (payload.content || '').trim();
        if (!content) return;
        const store = useChatStore.getState();
        const sessionId = ctx.sessionId ?? store.currentSessionId ?? (await store.createSession());
        if (isChatStreamBusyForSession(sessionId, store)) return;

        const userMessageId = generateId();
        const userMessage: Message = {
          id: userMessageId,
          role: 'user',
          content,
          createdAt: new Date().toISOString(),
        };
        store.addMessage(sessionId, userMessage);

        const assistantMsgId = generateId();
        const assistantMessage: Message = {
          id: assistantMsgId,
          role: 'assistant',
          content: '',
          createdAt: new Date().toISOString(),
          isStreaming: true,
          toolCalls: [],
        };
        store.addMessage(sessionId, assistantMessage);
        store.abortActiveStreamUnlessSession(sessionId);
        store.beginChatStreamSession(sessionId);
        store.setError(null);

        const controller = new AbortController();
        useChatStore.getState().setStreamAbortController(controller);

        try {
          await runChatStream({
            sessionId,
            userMessageId,
            assistantMsgId,
            content,
            modelMode: getComposerModelMode(),
            signal: controller.signal,
            t: tRef.current,
          });
        } catch (err) {
          handleChatStreamFailure(err, sessionId, assistantMsgId, tRef.current);
        } finally {
          useChatStore.getState().releaseChatStreamSessionAndResync(sessionId);
          useChatStore.getState().releaseStreamAbortController(controller);
        }
      },
      openArtifact(payload, ctx) {
        const messageId = payload.messageId ?? ctx.messageId;
        const artifacts = useArtifactStore.getState().artifacts;
        const candidate =
          (payload.artifactId && artifacts[payload.artifactId]) ||
          (messageId
            ? Object.values(artifacts).find(
                (a) =>
                  a.messageId === messageId &&
                  (payload.canvasId
                    ? (a.metadata as Record<string, unknown> | undefined)?.canvas_id === payload.canvasId
                    : a.type === 'html'),
              )
            : undefined);
        if (candidate) {
          useArtifactStore.getState().openTab(candidate.id);
        }
      },
      openFile(payload) {
        if (typeof window === 'undefined') return;
        const url = `/api/v1/files/${encodeURIComponent(payload.fileId)}/preview`;
        window.open(url, '_blank', 'noopener,noreferrer');
      },
      navigate(payload) {
        try {
          navRef.current(payload.route);
        } catch {
          if (typeof window !== 'undefined') window.location.href = payload.route;
        }
      },
      patchUi(payload, ctx) {
        const sessionId = payload.sessionId ?? ctx.sessionId;
        const messageId = payload.messageId ?? ctx.messageId;
        if (!sessionId || !messageId) return;
        useGenUiStore.getState().applyPatch(sessionId, messageId, { patches: payload.patches });
      },
      async runWorkflow(payload, ctx) {
        try {
          const res = await apiClient.post<WorkflowRunResponse>(
            `/workflow/flows/${payload.flowId}/run`,
            {
              input_data: payload.values ?? {},
              priority: 5,
              trigger_type: 'manual',
              session_id: ctx.sessionId ?? useChatStore.getState().currentSessionId,
            },
          );
          useExecutionOverlay.getState().start(res.prompt_id, 'chat');
          const sid = ctx.sessionId ?? useChatStore.getState().currentSessionId;
          if (sid) {
            useExecutionSessionStore.getState().upsertFromStarted(sid, {
              runId: res.execution_id,
              scope: 'workflow',
              promptId: res.prompt_id,
            });
          }
        } catch {
          /* GenUI surfaces errors inline when wired */
        }
      },
      async resumeWorkflow(payload, ctx) {
        try {
          await resumeWorkflowExecution({
            promptId: payload.promptId,
            answer: typeof payload.values?.answer === 'string' ? payload.values.answer : undefined,
            prompt: typeof payload.values?.prompt === 'string' ? payload.values.prompt : undefined,
            checkpointId:
              typeof payload.values?.checkpoint_id === 'string'
                ? payload.values.checkpoint_id
                : undefined,
          });
          useExecutionOverlay.getState().setBlocked(payload.promptId, null);
          const sid = ctx.sessionId ?? useChatStore.getState().currentSessionId;
          if (sid) {
            useExecutionSessionStore.getState().setPromptId(sid, payload.promptId);
          }
        } catch {
          /* GenUI surfaces errors inline when wired */
        }
      },
    });
  }, []);

  return null;
}
