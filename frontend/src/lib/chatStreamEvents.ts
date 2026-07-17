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
  SessionTodosEventPayload,
  ToolCall,
  UserInputQuestion,
} from '@/types/chat';
import { normalizeAttachmentList } from '@/types/chat';
import { useExecutionSessionStore } from '@/stores/executionSession';
import { useExecutionOverlay } from '@/features/workflow/store/executionOverlay';
import type {
  GenUiTreeV1,
  UiPatchStreamPayload,
  UiTreeStreamPayload,
} from '@/types/genUi';
import { isDocProcessorWriteStream } from '@/lib/docProcessorStreamPreview';

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

/** Tools that auto-focus the workspace Code tab when they start running. */
const CODE_TAB_AUTO_FOCUS_TOOLS: ReadonlySet<string> = new Set([
  'coding_agent',
  'code_execution',
  'canvas_publish',
  'project_shell',
  'project_write',
  'project_edit',
  'project_multiedit',
  'project_apply_patch',
  'coding_project_run',
]);

// ---------------------------------------------------------------------------
// Content delta batching: accumulate text chunks and flush once per animation
// frame to reduce DOM update frequency and eliminate frame drops during fast
// token streams.
// ---------------------------------------------------------------------------
const _contentBatchBuffers = new Map<string, string>();
let _contentBatchRafId: number | null = null;

function _flushContentBatch(): void {
  _contentBatchRafId = null;
  const s = useChatStore.getState();
  for (const [key, text] of _contentBatchBuffers) {
    const [sessionId, msgId] = key.split('\0', 2);
    if (sessionId && msgId) {
      s.appendToMessage(sessionId, msgId, text);
    }
  }
  _contentBatchBuffers.clear();
}

function _batchContentDelta(sessionId: string, msgId: string, text: string): void {
  const key = `${sessionId}\0${msgId}`;
  const existing = _contentBatchBuffers.get(key);
  _contentBatchBuffers.set(key, existing ? existing + text : text);
  if (_contentBatchRafId === null) {
    _contentBatchRafId = requestAnimationFrame(_flushContentBatch);
  }
}

export function flushPendingContentBatch(): void {
  if (_contentBatchRafId !== null) {
    cancelAnimationFrame(_contentBatchRafId);
    _flushContentBatch();
  }
  if (_thinkingBatchRafId !== null) {
    cancelAnimationFrame(_thinkingBatchRafId);
    _flushThinkingBatch();
  }
  if (_toolDeltaBatchRafId !== null) {
    cancelAnimationFrame(_toolDeltaBatchRafId);
    _flushToolDeltaBatch();
  }
}

// ---------------------------------------------------------------------------
// Thinking delta batching: same rAF pattern as content to avoid per-event
// re-renders during DeepSeek's often long reasoning phase.
// ---------------------------------------------------------------------------
const _thinkingBatchBuffers = new Map<string, string>();
let _thinkingBatchRafId: number | null = null;

function _flushThinkingBatch(): void {
  _thinkingBatchRafId = null;
  const s = useChatStore.getState();
  for (const [key, text] of _thinkingBatchBuffers) {
    const [sessionId, msgId] = key.split('\0', 2);
    if (sessionId && msgId) {
      s.updateMessage(sessionId, msgId, { thinking: text });
    }
  }
  _thinkingBatchBuffers.clear();
}

function _batchThinkingDelta(sessionId: string, msgId: string, text: string): void {
  const key = `${sessionId}\0${msgId}`;
  _thinkingBatchBuffers.set(key, text);
  if (_thinkingBatchRafId === null) {
    _thinkingBatchRafId = requestAnimationFrame(_flushThinkingBatch);
  }
}

// ---------------------------------------------------------------------------
// Tool-call delta batching: coding/canvas tools can emit many partial JSON
// frames. Keep only the latest snapshot per tool call and flush once per frame.
// ---------------------------------------------------------------------------
interface ToolDeltaSnapshot {
  sessionId: string;
  msgId: string;
  toolCallId: string;
  name: string;
  index: number;
  argumentsRaw: string;
  argumentsPartial: Record<string, unknown>;
}

const _toolDeltaBatchBuffers = new Map<string, ToolDeltaSnapshot>();
let _toolDeltaBatchRafId: number | null = null;

function _flushToolDeltaBatch(): void {
  _toolDeltaBatchRafId = null;
  const s = useChatStore.getState();
  for (const snapshot of _toolDeltaBatchBuffers.values()) {
    const prev =
      s.messages[snapshot.sessionId]?.find((m) => m.id === snapshot.msgId)?.toolCalls ?? [];
    const existingIdx = prev.findIndex((tc) => tc.id === snapshot.toolCallId);
    if (existingIdx === -1) {
      s.updateMessage(snapshot.sessionId, snapshot.msgId, {
        toolCalls: [
          ...prev,
          {
            id: snapshot.toolCallId,
            name: snapshot.name,
            arguments: snapshot.argumentsPartial,
            argumentsRaw: snapshot.argumentsRaw,
            toolCallIndex: snapshot.index,
            status: 'running',
          },
        ],
      });
    } else {
      s.updateToolCall(snapshot.sessionId, snapshot.msgId, snapshot.toolCallId, {
        argumentsRaw: snapshot.argumentsRaw,
        ...(Object.keys(snapshot.argumentsPartial).length > 0
          ? { arguments: snapshot.argumentsPartial }
          : {}),
        ...(snapshot.name !== 'unknown_tool' ? { name: snapshot.name } : {}),
        toolCallIndex: snapshot.index,
      });
    }
  }
  _toolDeltaBatchBuffers.clear();
}

function _batchToolCallDelta(snapshot: ToolDeltaSnapshot): void {
  const key = `${snapshot.sessionId}\0${snapshot.msgId}\0${snapshot.toolCallId}`;
  _toolDeltaBatchBuffers.set(key, snapshot);
  if (_toolDeltaBatchRafId === null) {
    _toolDeltaBatchRafId = requestAnimationFrame(_flushToolDeltaBatch);
  }
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
      _batchContentDelta(sessionId, assistantMsgId, String(event.data ?? ''));
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

      _batchToolCallDelta({
        sessionId,
        msgId: assistantMsgId,
        toolCallId: tid,
        name: nameGuess,
        index: idx,
        argumentsRaw: raw,
        argumentsPartial: partialArgs,
      });
      if (nameGuess === 'canvas_publish' || nameGuess === 'code_execution') {
        useLayoutStore.setState({ workspaceOpen: true, workspaceTab: 'agent' });
      }
      if (
        (nameGuess === 'text_processor' || nameGuess === 'markdown_processor') &&
        isDocProcessorWriteStream(nameGuess, raw, partialArgs)
      ) {
        useLayoutStore.setState({ workspaceOpen: true, workspaceTab: 'files' });
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
      if (_toolDeltaBatchRafId !== null) {
        cancelAnimationFrame(_toolDeltaBatchRafId);
        _flushToolDeltaBatch();
      }
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
        // Update by real ID and also remove any orphaned placeholder for same tool name.
        nextToolCalls = prevArr
          .filter((tc, i) => {
            if (i === bySameId) return true;
            if (tc.id.startsWith('__delta_') && tc.name === toolName && tc.status === 'running') return false;
            return true;
          })
          .map((tc) =>
            tc.id === realId ? { ...tc, ...toolCall, argumentsRaw: undefined } : tc,
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
      useExecutionSessionStore.getState().appendCapability(sessionId, {
        id: realId,
        toolCallId: realId,
        name: toolName,
        status: 'running',
        timestamp: new Date().toISOString(),
      });
      if (CODE_TAB_AUTO_FOCUS_TOOLS.has(toolName)) {
        useLayoutStore.setState({ workspaceOpen: true, workspaceTab: 'agent' });
      }
      break;
    }

    case 'tool_result': {
      const tr = event.data as {
        id?: string;
        tool_call_id?: string;
        tool_use_id?: string;
        name?: string;
        data?: unknown;
        result?: unknown;
        content?: unknown;
        envelope?: { data?: unknown };
        error?: string;
        success?: boolean;
        duration_ms?: number;
      };
      const toolCallId = tr.id || tr.tool_call_id || tr.tool_use_id || '';
      let structured: unknown =
        tr.data !== undefined && tr.data !== null
          ? tr.data
          : tr.envelope?.data !== undefined && tr.envelope?.data !== null
            ? tr.envelope.data
            : tr.result ?? tr.content;
      // History / truncated SSE often leave a JSON string — normalize to object.
      if (typeof structured === 'string') {
        const trimmed = structured.trim();
        if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
          try {
            structured = JSON.parse(trimmed) as unknown;
          } catch {
            /* keep string */
          }
        }
      }
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
      useExecutionSessionStore.getState().updateCapability(sessionId, toolCallId, {
        status: tr.error || !tr.success ? 'error' : 'success',
        error: tr.error,
        name: toolNameTr || undefined,
      });
      break;
    }

    case 'thinking': {
      const raw = event.data;
      let thought = '';
      if (typeof raw === 'string') {
        thought = raw;
      } else if (raw && typeof raw === 'object') {
        const rec = raw as { thought?: unknown; content?: unknown };
        if (typeof rec.thought === 'string') {
          thought = rec.thought;
        } else if (typeof rec.content === 'string') {
          thought = rec.content;
        }
      }
      if (thought) {
        _batchThinkingDelta(sessionId, assistantMsgId, thought);
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
      // Merge by id so newly versioned attachments (new file_id after overwrite)
      // appear immediately; query invalidation refreshes the full session list.
      const byId = new Map(prev.map((a) => [a.id, a]));
      for (const att of hydrated) {
        byId.set(att.id, att);
      }
      s.updateMessage(sessionId, assistantMsgId, {
        attachments: Array.from(byId.values()),
      });
      void queryClient.invalidateQueries({
        queryKey: ['chat', 'session-attachments', sessionId],
      });
      break;
    }

    case 'assistant_media': {
      const payload = event.data as AttachmentEventPayload & { native?: boolean };
      const hydrated: Attachment[] = normalizeAttachmentList(payload?.attachments);
      if (hydrated.length === 0) break;
      const msg = s.messages[sessionId]?.find((m) => m.id === assistantMsgId);
      const prev = msg?.inlineMedia ?? [];
      const seen = new Set(prev.map((a) => a.id));
      const merged = [...prev, ...hydrated.filter((a) => !seen.has(a.id))];
      s.updateMessage(sessionId, assistantMsgId, {
        inlineMedia: merged,
        nativeMedia: Boolean(payload?.native) || Boolean(msg?.nativeMedia),
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
      const checkpointIdFromRequest = typeof d.checkpoint_id === 'string' ? d.checkpoint_id : undefined;
      const payload: PendingUserInput = {
        sessionId,
        assistantMsgId,
        toolCallId,
        questions,
        checkpointId: checkpointIdFromRequest,
      };
      s.setPendingUserInput(payload);
      s.updateToolCall(sessionId, assistantMsgId, toolCallId, { status: 'awaiting_user' });
      useExecutionSessionStore.getState().updateCapability(sessionId, toolCallId, {
        status: 'awaiting_user',
      });
      break;
    }

    case 'execution_started': {
      const d = event.data as {
        run_id?: string;
        session_id?: string;
        scope?: string;
        prompt_id?: string | null;
        parent_run_id?: string | null;
      };
      const runId = typeof d.run_id === 'string' ? d.run_id : '';
      if (!runId) break;
      useExecutionSessionStore.getState().upsertFromStarted(sessionId, {
        runId,
        scope: typeof d.scope === 'string' ? d.scope : undefined,
        promptId: typeof d.prompt_id === 'string' ? d.prompt_id : d.prompt_id ?? undefined,
        parentRunId: typeof d.parent_run_id === 'string' ? d.parent_run_id : undefined,
      });
      break;
    }

    case 'agent_task': {
      const d = event.data as { task_id?: string; session_id?: string };
      const taskId = typeof d.task_id === 'string' ? d.task_id : '';
      if (!taskId) break;
      useExecutionSessionStore.getState().setAgentTaskId(sessionId, taskId);
      break;
    }

    case 'workflow_done': {
      const d = event.data as {
        prompt_id?: string;
        run_id?: string;
        success?: boolean;
        pause_token?: Record<string, unknown> | null;
      };
      useExecutionSessionStore.getState().markWorkflowDone(sessionId, {
        promptId: typeof d.prompt_id === 'string' ? d.prompt_id : undefined,
        runId: typeof d.run_id === 'string' ? d.run_id : undefined,
        success: d.success,
      });
      if (d.pause_token) {
        useExecutionSessionStore.getState().setPauseToken(sessionId, d.pause_token);
      }
      if (typeof d.prompt_id === 'string' && d.prompt_id) {
        useExecutionOverlay.getState().finish(
          d.prompt_id,
          d.success === false ? { errors: ['Workflow step failed'] } : undefined,
        );
      }
      break;
    }

    case 'task_progress': {
      const payload = event.data as TaskProgressEventPayload;
      if (!payload?.task_id || !payload?.label || !payload?.status) break;
      const step = {
        taskId: payload.task_id,
        label: payload.label,
        status: payload.status,
        order: payload.order,
        progress: payload.progress,
      };
      s.upsertTaskProgress(sessionId, assistantMsgId, step);
      s.upsertSessionTodoFromProgress(sessionId, step);
      break;
    }

    case 'session_todos': {
      const payload = event.data as SessionTodosEventPayload;
      if (!Array.isArray(payload?.todos)) break;
      s.setSessionTodos(
        sessionId,
        payload.todos.map((item, index) => ({
          taskId: String(item.id),
          label: String(item.content || item.id),
          status: item.status,
          order: item.order ?? index,
        })),
      );
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
      // A single turn may emit BOTH a DAG embed and a step card. Keep them on
      // the same message instead of clearing one another (otherwise the DAG
      // would flash then disappear when the step card arrives, and vice versa).
      if (d.embed && typeof d.embed.digest === 'string' && d.embed.data && typeof d.embed.data === 'object') {
        const prevEmbed = s.messages[sessionId]?.find((m) => m.id === assistantMsgId)?.workflowEmbed;
        const emb: ChatWorkflowEmbedState = {
          data: d.embed.data as Record<string, unknown>,
          digest: d.embed.digest,
          title: typeof d.embed.title === 'string' ? d.embed.title : undefined,
          summary: typeof d.embed.summary === 'string' ? d.embed.summary : undefined,
          flowId: typeof d.embed.flow_id === 'string' ? d.embed.flow_id : undefined,
          // Preserve in-flight run state across a re-emit of the same graph.
          ...(prevEmbed && prevEmbed.digest === d.embed.digest && prevEmbed.run
            ? { run: prevEmbed.run }
            : {}),
        };
        s.updateMessage(sessionId, assistantMsgId, { workflowEmbed: emb });
        break;
      }
      if (!d?.spec || typeof d.digest !== 'string') break;
      const prev = s.messages[sessionId]?.find((m) => m.id === assistantMsgId)?.workflow;
      s.updateMessage(sessionId, assistantMsgId, {
        workflow: {
          spec: d.spec,
          digest: d.digest,
          stepRuns: prev?.stepRuns ?? {},
        },
      });
      break;
    }

    case 'error': {
      const errData = event.data as { message?: string; terminal_reason?: string } | undefined;
      const errReason = errData?.terminal_reason;

      // Use reason-aware error messages when available.
      let errMessage: string;
      if (errReason === 'prompt_too_long') {
        errMessage = t('chat.errors.promptTooLong', {
          defaultValue: 'The conversation is too long for the model context window. Try starting a new chat or compacting the context.',
        });
      } else if (errReason === 'model_error') {
        errMessage = errData?.message || t('chat.errors.modelError', {
          defaultValue: 'The model returned an error. Please try again.',
        });
      } else {
        errMessage = errData?.message || t('chat.errors.stream');
      }
      s.setError(errMessage);
      s.finalizeToolCalls(sessionId, assistantMsgId, 'error');
      if (errReason) {
        useChatStore.setState({ lastTerminalReason: errReason });
      }
      break;
    }

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

      // Capture terminal_reason + checkpoint_id for differentiated
      // end-of-turn UI (e.g. "turn limit reached", resume button).
      const acData = event.data as Record<string, unknown> | undefined;
      if (acData) {
        const terminalReason = typeof acData.terminal_reason === 'string'
          ? acData.terminal_reason
          : null;
        const checkpointId = typeof acData.checkpoint_id === 'string'
          ? acData.checkpoint_id
          : null;
        s.lastTerminalReason = terminalReason;
        s.lastCheckpointId = checkpointId;
        useChatStore.setState({ lastTerminalReason: terminalReason, lastCheckpointId: checkpointId });
      }

      const pending = useChatStore.getState().pendingUserInput;
      const pauseToken =
        acData && typeof acData.pause_token === 'object' && acData.pause_token !== null
          ? (acData.pause_token as Record<string, unknown>)
          : null;
      const terminalReason =
        acData && typeof acData.terminal_reason === 'string' ? acData.terminal_reason : null;
      const awaitingInput =
        terminalReason === 'awaiting_user_input' ||
        pauseToken != null ||
        (pending?.sessionId === sessionId && Boolean(pending.checkpointId));

      if (awaitingInput) {
        useExecutionSessionStore.getState().setStatus(sessionId, 'blocked');
        if (pauseToken) {
          useExecutionSessionStore.getState().setPauseToken(sessionId, pauseToken);
        }
      } else {
        useExecutionSessionStore.getState().setStatus(sessionId, 'completed');
      }
      break;
    }

    default:
      break;
  }
}
