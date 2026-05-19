import { queryClient } from '@/lib/queryClient';
import { useLayoutStore } from '@/stores/layout';
import { useChatStore } from '@/stores/chat';
import { useArtifactStore } from '@/stores/artifact';
import { useCodeArtifactStore, type CodeArtifactEntry } from '@/stores/codeArtifact';
import { useGenUiStore } from '@/stores/genUi';
import { generateId } from '@/lib/utils';
import { getCachedPetBubbleGreeting } from '@/hooks/useDailyChatGreetings';
import type {
  Attachment,
  AttachmentEventPayload,
  ChatWorkflowEmbedState,
  ChatWorkflowSpecModel,
  Message,
  MessageUsage,
  PendingUserInput,
  PetBubblePayload,
  TaskProgressEventPayload,
  ToolCall,
  UserInputQuestion,
} from '@/types/chat';
import { normalizeAttachmentList } from '@/types/chat';
import type { GenUiTreeV1, UiPatchStreamPayload, UiTreeStreamPayload } from '@/types/genUi';

export type ChatStreamTranslate = (
  key: string,
  options?: { defaultValue?: string },
) => string;

export interface ApplyChatStreamEventParams {
  sessionId: string;
  assistantMsgId: string;
  userMessageId: string;
  t: ChatStreamTranslate;
}

export const PET_DAILY_FALLBACK_GREETING_KEYS = [
  'chat.petBubble.dailyGreeting1',
  'chat.petBubble.dailyGreeting2',
  'chat.petBubble.dailyGreeting3',
  'chat.petBubble.dailyGreeting4',
  'chat.petBubble.dailyGreeting5',
  'chat.petBubble.dailyGreeting6',
  'chat.petBubble.dailyGreeting7',
  'chat.petBubble.dailyGreeting8',
  'chat.petBubble.dailyGreeting9',
  'chat.petBubble.dailyGreeting10',
] as const;

export function petDailyFallbackGreetingKey(date = new Date()): string {
  const dayNumber = Math.floor(
    Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / 86_400_000,
  );
  const index = ((dayNumber % PET_DAILY_FALLBACK_GREETING_KEYS.length) +
    PET_DAILY_FALLBACK_GREETING_KEYS.length) %
    PET_DAILY_FALLBACK_GREETING_KEYS.length;
  return PET_DAILY_FALLBACK_GREETING_KEYS[index]!;
}

function shouldShowFallbackPetBubble(message: Message | undefined): boolean {
  if (!message || message.petBubble?.text) return false;
  if (message.content.trim()) return true;
  if (message.thinking?.trim()) return true;
  if (message.workflow || message.workflowEmbed || message.genUiReplay) return true;
  if (message.toolCalls?.some((tc) => tc.name !== 'emit_pet_bubble')) return true;
  if (message.taskProgress?.length) return true;
  if (message.attachments?.length) return true;
  return false;
}

/**
 * Shared handler for `/chat/stream` SSE events (ChatView, ChatPanel, or any other consumer).
 */
export function applyChatStreamEvent(
  event: { type?: string; data?: unknown },
  p: ApplyChatStreamEventParams,
): void {
  const { sessionId, assistantMsgId, userMessageId, t } = p;
  const type = event.type;
  if (!type) return;

  const s = useChatStore.getState();

  switch (type) {
    case 'content':
      s.appendToMessage(sessionId, assistantMsgId, String(event.data ?? ''));
      break;

    case 'tool_call_delta': {
      const d = event.data as Record<string, unknown>;
      const idx =
        typeof d.index === 'number'
          ? d.index
          : Number.isFinite(Number(d.index))
            ? Number(d.index)
            : 0;
      const tid =
        typeof d.id === 'string' && d.id.trim().length > 0 ? d.id.trim() : `__delta_${idx}`;
      const raw = typeof d.arguments_raw === 'string' ? d.arguments_raw : '';
      const partialRaw = d.arguments_partial;
      const partialArgs =
        partialRaw && typeof partialRaw === 'object' && !Array.isArray(partialRaw)
          ? (partialRaw as Record<string, unknown>)
          : {};
      const nameGuess =
        typeof d.name === 'string' && d.name.trim().length > 0 ? d.name.trim() : 'unknown_tool';

      const prev =
        s.messages[sessionId]?.find((m) => m.id === assistantMsgId)?.toolCalls ?? [];
      const existingIdx = prev.findIndex((tc) => tc.id === tid);
      if (existingIdx === -1) {
        s.updateMessage(sessionId, assistantMsgId, {
          toolCalls: [
            ...prev,
            {
              id: tid,
              name: nameGuess,
              arguments: partialArgs,
              argumentsRaw: raw,
              toolCallIndex: idx,
              status: 'running',
            },
          ],
        });
      } else {
        s.updateToolCall(sessionId, assistantMsgId, tid, {
          argumentsRaw: raw,
          ...(Object.keys(partialArgs).length > 0 ? { arguments: partialArgs } : {}),
          ...(nameGuess !== 'unknown_tool' ? { name: nameGuess } : {}),
          toolCallIndex: idx,
        });
      }
      if (nameGuess === 'canvas_publish' || nameGuess === 'code_execution') {
        useLayoutStore.setState({ workspaceOpen: true, workspaceTab: 'agent' });
      }
      break;
    }

    case 'nested_agent_preview': {
      const d = event.data as Record<string, unknown>;
      const parentId =
        typeof d.parent_tool_call_id === 'string' ? d.parent_tool_call_id.trim() : '';
      const name = typeof d.name === 'string' ? d.name.trim() : '';
      const raw = typeof d.arguments_raw === 'string' ? d.arguments_raw : '';
      const partial = d.arguments_partial;
      const partialArgs =
        partial && typeof partial === 'object' && !Array.isArray(partial)
          ? (partial as Record<string, unknown>)
          : undefined;
      if (parentId && name) {
        s.setNestedAgentPreview(sessionId, {
          parentToolCallId: parentId,
          toolName: name,
          argumentsRaw: raw,
          ...(partialArgs ? { argumentsPartial: partialArgs } : {}),
        });
        useLayoutStore.setState({ workspaceOpen: true, workspaceTab: 'agent' });
      }
      break;
    }

    case 'tool_call': {
      const d = event.data as Record<string, unknown>;
      const toolName = String(d.name ?? '');
      const realId = (d.id as string) || generateId();
      const prevArr =
        s.messages[sessionId]?.find((m) => m.id === assistantMsgId)?.toolCalls ?? [];

      const bySameId = prevArr.findIndex((tc) => tc.id === realId);
      const placeholderIdx = prevArr.findIndex(
        (tc) =>
          tc.name === toolName &&
          tc.status === 'running' &&
          tc.id.startsWith('__delta_'),
      );

      const toolCall: ToolCall = {
        id: realId,
        name: toolName,
        arguments: (d.arguments as Record<string, unknown>) ?? {},
        status: 'running',
      };

      let nextToolCalls: ToolCall[];
      if (bySameId !== -1) {
        nextToolCalls = prevArr.map((tc, i) =>
          i === bySameId ? { ...tc, ...toolCall, argumentsRaw: undefined } : tc,
        );
      } else if (placeholderIdx !== -1) {
        const ph = prevArr[placeholderIdx];
        nextToolCalls = prevArr.map((tc, i) =>
          i === placeholderIdx
            ? {
                ...toolCall,
                argumentsRaw: ph?.argumentsRaw,
                toolCallIndex: ph?.toolCallIndex,
              }
            : tc,
        );
      } else {
        nextToolCalls = [...prevArr, toolCall];
      }

      s.updateMessage(sessionId, assistantMsgId, {
        toolCalls: nextToolCalls,
      });
      if (
        toolName === 'coding_agent' ||
        toolName === 'code_execution' ||
        toolName === 'canvas_publish'
      ) {
        useLayoutStore.setState({ workspaceOpen: true, workspaceTab: 'agent' });
      }
      break;
    }

    case 'tool_result': {
      const tr = event.data as {
        id?: string;
        tool_call_id?: string;
        name?: string;
        data?: unknown;
        result?: unknown;
        content?: unknown;
        error?: string;
        success?: boolean;
        duration_ms?: number;
      };
      const toolCallId = tr.id || tr.tool_call_id || '';
      const structured = tr.data !== undefined && tr.data !== null ? tr.data : tr.result ?? tr.content;
      const toolNameTr = typeof tr.name === 'string' ? tr.name : '';
      s.updateToolCall(sessionId, assistantMsgId, toolCallId, {
        result: structured,
        status: tr.error || !tr.success ? 'error' : 'success',
        error: tr.error,
        duration_ms: tr.duration_ms,
        ...(toolNameTr === 'canvas_publish' ? { argumentsRaw: undefined } : {}),
      });
      if (toolNameTr === 'coding_agent') {
        s.setNestedAgentPreview(sessionId, null);
      }
      break;
    }

    case 'thinking': {
      const thought =
        typeof event.data === 'string'
          ? event.data
          : (event.data as { content?: string })?.content ?? '';
      if (thought) {
        s.updateMessage(sessionId, assistantMsgId, { thinking: thought });
      }
      break;
    }

    case 'context_usage': {
      const raw = event.data as Partial<MessageUsage> | undefined;
      if (!raw || typeof raw !== 'object') break;
      const pt = raw.prompt_tokens;
      const ct = raw.completion_tokens;
      const tt = raw.total_tokens;
      const hasPrompt = typeof pt === 'number' && Number.isFinite(pt);
      const hasCompletion = typeof ct === 'number' && Number.isFinite(ct);
      const hasTotal = typeof tt === 'number' && Number.isFinite(tt);
      if (!hasPrompt && !hasCompletion && !hasTotal) break;

      const prompt_tokens = hasPrompt ? pt : 0;
      const completion_tokens = hasCompletion ? ct : 0;
      const total_tokens = hasTotal ? tt : prompt_tokens + completion_tokens;

      const usage: MessageUsage = {
        prompt_tokens,
        completion_tokens,
        total_tokens,
        ...(typeof raw.reasoning_tokens === 'number'
          ? { reasoning_tokens: raw.reasoning_tokens }
          : {}),
        ...(typeof raw.prompt_cache_hit_tokens === 'number'
          ? { prompt_cache_hit_tokens: raw.prompt_cache_hit_tokens }
          : {}),
        ...(typeof raw.prompt_cache_miss_tokens === 'number'
          ? { prompt_cache_miss_tokens: raw.prompt_cache_miss_tokens }
          : {}),
      };
      s.updateMessage(sessionId, assistantMsgId, { usage });
      break;
    }

    case 'attachments': {
      const payload = event.data as AttachmentEventPayload;
      const hydrated: Attachment[] = normalizeAttachmentList(payload?.attachments);
      s.updateMessage(sessionId, userMessageId, { attachments: hydrated });
      break;
    }

    case 'workspace_attachments': {
      const payload = event.data as AttachmentEventPayload;
      const hydrated: Attachment[] = normalizeAttachmentList(payload?.attachments);
      if (hydrated.length === 0) break;
      const prev =
        s.messages[sessionId]?.find((m) => m.id === assistantMsgId)?.attachments ?? [];
      s.updateMessage(sessionId, assistantMsgId, {
        attachments: [...prev, ...hydrated],
      });
      void queryClient.invalidateQueries({
        queryKey: ['chat', 'session-attachments', sessionId],
      });
      break;
    }

    case 'user_input_request': {
      const d = event.data as Record<string, unknown>;
      const tc = d.tool_call as Record<string, unknown> | undefined;
      const toolCallId = typeof tc?.id === 'string' ? tc.id : '';
      const rawQs = d.questions;
      const questions: UserInputQuestion[] = [];
      if (Array.isArray(rawQs)) {
        for (const item of rawQs) {
          if (!item || typeof item !== 'object') continue;
          const o = item as Record<string, unknown>;
          const id = typeof o.id === 'string' ? o.id : '';
          const prompt = typeof o.prompt === 'string' ? o.prompt : '';
          if (!id || !prompt) continue;
          const q: UserInputQuestion = { id, prompt };
          if (Array.isArray(o.choices)) {
            q.choices = o.choices.filter((c): c is string => typeof c === 'string' && c.length > 0);
          }
          if (typeof o.allow_custom === 'boolean') q.allow_custom = o.allow_custom;
          if (typeof o.multi_select === 'boolean') q.multi_select = o.multi_select;
          if (o.ui_variant === 'questionnaire' || o.ui_variant === 'permission') {
            q.ui_variant = o.ui_variant;
          }
          if (
            o.permission_kind === 'file_access' ||
            o.permission_kind === 'tool_run' ||
            o.permission_kind === 'mode_change' ||
            o.permission_kind === 'generic'
          ) {
            q.permission_kind = o.permission_kind;
          }
          if (typeof o.detail === 'string' && o.detail.trim()) q.detail = o.detail.trim();
          if (typeof o.primary_choice === 'string' && o.primary_choice.trim()) {
            q.primary_choice = o.primary_choice.trim();
          }
          if (typeof o.secondary_choice === 'string' && o.secondary_choice.trim()) {
            q.secondary_choice = o.secondary_choice.trim();
          }
          questions.push(q);
        }
      }
      if (!toolCallId || questions.length === 0) break;
      const payload: PendingUserInput = {
        sessionId,
        assistantMsgId,
        toolCallId,
        questions,
      };
      s.setPendingUserInput(payload);
      s.updateToolCall(sessionId, assistantMsgId, toolCallId, { status: 'awaiting_user' });
      break;
    }

    case 'task_progress': {
      const payload = event.data as TaskProgressEventPayload;
      if (!payload?.task_id || !payload?.label || !payload?.status) break;
      s.upsertTaskProgress(sessionId, assistantMsgId, {
        taskId: payload.task_id,
        label: payload.label,
        status: payload.status,
        order: payload.order,
        progress: payload.progress,
      });
      break;
    }

    case 'workflow': {
      const d = event.data as {
        spec?: ChatWorkflowSpecModel;
        digest?: string;
        partial?: boolean;
        embed?: {
          data?: unknown;
          digest?: string;
          title?: string;
          summary?: string;
          flow_id?: string;
        };
      };
      if (d.embed && typeof d.embed.digest === 'string' && d.embed.data && typeof d.embed.data === 'object') {
        const emb: ChatWorkflowEmbedState = {
          data: d.embed.data as Record<string, unknown>,
          digest: d.embed.digest,
          title: typeof d.embed.title === 'string' ? d.embed.title : undefined,
          summary: typeof d.embed.summary === 'string' ? d.embed.summary : undefined,
          flowId: typeof d.embed.flow_id === 'string' ? d.embed.flow_id : undefined,
        };
        s.updateMessage(sessionId, assistantMsgId, { workflowEmbed: emb, workflow: undefined });
        break;
      }
      if (!d?.spec || typeof d.digest !== 'string') break;
      const prev = s.messages[sessionId]?.find((m) => m.id === assistantMsgId)?.workflow;
      s.updateMessage(sessionId, assistantMsgId, {
        workflowEmbed: undefined,
        workflow: {
          spec: d.spec,
          digest: d.digest,
          stepRuns: prev?.stepRuns ?? {},
        },
      });
      break;
    }

    case 'error':
      s.setError(
        (event.data as { message?: string })?.message || t('chat.errors.stream'),
      );
      s.finalizeToolCalls(sessionId, assistantMsgId, 'error');
      break;

    case 'canvas': {
      const d = event.data as Record<string, unknown>;
      const previewPath = typeof d.preview_path === 'string' ? d.preview_path : '';
      if (!previewPath) break;
      const id = String(d.id || generateId());
      useArtifactStore.getState().addArtifact({
        id,
        type: 'html',
        title: String(d.title || 'Canvas'),
        content: '',
        createdAt: new Date().toISOString(),
        sessionId,
        messageId: assistantMsgId,
        metadata: {
          previewPath,
          canvasId: d.canvas_id,
          revision: d.revision,
          trust: d.trust ?? 'hosted',
          contentType: d.content_type,
        },
      });
      if (d.open_in_panel !== false) {
        useArtifactStore.getState().openTab(id);
      }
      break;
    }

    case 'ui_tree': {
      const raw = event.data as { tree?: unknown; canvas_id?: string; tool_call_id?: string };
      if (raw?.tree && typeof raw.tree === 'object') {
        const tree = raw.tree as GenUiTreeV1;
        const payload: UiTreeStreamPayload = {
          tree,
          canvas_id: raw.canvas_id,
          tool_call_id: raw.tool_call_id,
        };
        useGenUiStore.getState().setFromStream(sessionId, assistantMsgId, payload);
      }
      break;
    }

    case 'ui_patch': {
      const data = event.data as UiPatchStreamPayload;
      if (data?.patches && Array.isArray(data.patches)) {
        useGenUiStore.getState().applyPatch(
          sessionId,
          assistantMsgId,
          data,
        );
      }
      break;
    }

    case 'pet_bubble': {
      const raw = event.data as Record<string, unknown> | undefined;
      const text = typeof raw?.text === 'string' ? raw.text.trim() : '';
      if (!text) break;
      const payload: PetBubblePayload = { text };
      const em = raw?.emoji;
      if (typeof em === 'string' && em.trim()) {
        payload.emoji = em.trim().slice(0, 16);
      }
      s.updateMessage(sessionId, assistantMsgId, { petBubble: payload });
      break;
    }

    case 'message_ids': {
      const d = event.data as {
        user_message_id?: string;
        assistant_message_id?: string;
      };
      s.remapStreamPersistedIds(sessionId, {
        clientUserId: userMessageId,
        serverUserId: d.user_message_id,
        clientAssistantId: assistantMsgId,
        serverAssistantId: d.assistant_message_id,
      });
      break;
    }

    case 'code_artifact': {
      const d = event.data as Record<string, unknown>;
      const artifactId = typeof d.artifact_id === 'string' ? d.artifact_id : '';
      if (artifactId) {
        const diagnosticsRaw = Array.isArray(d.diagnostics) ? d.diagnostics : undefined;
        const diagnostics = diagnosticsRaw?.map((diag: Record<string, unknown>) => ({
          message: typeof diag.message === 'string' ? diag.message : '',
          line: typeof diag.line === 'number' ? diag.line : undefined,
          column: typeof diag.column === 'number' ? diag.column : undefined,
        }));
        useCodeArtifactStore.getState().addEntry({
          artifactId,
          kind: (d.kind as CodeArtifactEntry['kind']) ?? 'execute',
          language: typeof d.language === 'string' ? d.language : 'python',
          originTool: typeof d.origin_tool === 'string' ? d.origin_tool : '',
          targetPath: typeof d.target_path === 'string' ? d.target_path : undefined,
          syntaxValid: typeof d.syntax_valid === 'boolean' ? d.syntax_valid : null,
          diagnostics,
          sessionId,
          receivedAt: new Date().toISOString(),
        });
      }
      break;
    }

    case 'assistant_complete': {
      // Per-message only: hide the streaming caret. Do not clear global
      // isStreaming here — that stays true until the HTTP stream completes
      // so Stop stays effective during DB persist and tail events.
      const current = s.messages[sessionId]?.find((m) => m.id === assistantMsgId);
      let fallbackBubble: { petBubble: PetBubblePayload } | Record<string, never> = {};
      if (shouldShowFallbackPetBubble(current)) {
        const cached = getCachedPetBubbleGreeting();
        fallbackBubble = {
          petBubble: {
            text:
              cached ??
              t(petDailyFallbackGreetingKey(), {
                defaultValue: 'All set - see my reply here.',
              }),
          },
        };
      }
      s.updateMessage(sessionId, assistantMsgId, {
        isStreaming: false,
        ...fallbackBubble,
      });
      break;
    }

    default:
      break;
  }
}
