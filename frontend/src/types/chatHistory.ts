/**
 * History parity: API rows → Message mirrors live chat when extensions include
 * ``thinking``, ``task_progress``, ``gen_ui``, ``pet_bubble`` (merged on stream persist), plus
 * workflow keys from ``parseWorkflow*FromExtensions``. Canvas artifacts stay client-local.
 */
import type { Message, PetBubblePayload, TaskProgressStep, ToolCall } from '@/types/chat';
import {
  normalizeAttachmentList,
  parseWorkflowEmbedFromExtensions,
  parseWorkflowFromExtensions,
} from '@/types/chat';
import type { GenUiTreeV1 } from '@/types/genUi';

export interface MessageResponse {
  id: string;
  session_id?: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  status?: string;
  model?: string;
  tool_calls?: unknown;
  tool_call_id?: string | null;
  attachments?: unknown;
  extensions?: string | Record<string, unknown> | null;
  created_at: string;
  rating?: number | null;
  /** Provider prompt-side tokens persisted on assistant rows (maps to ``usage.prompt_tokens``). */
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
}

type UnknownRecord = Record<string, unknown>;

function asRecord(value: unknown): UnknownRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as UnknownRecord)
    : null;
}

function parseJsonString(value: unknown): unknown {
  if (typeof value !== 'string') return value;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
}

function asStatus(value: unknown, fallback: ToolCall['status']): ToolCall['status'] {
  return value === 'pending' ||
    value === 'running' ||
    value === 'awaiting_user' ||
    value === 'success' ||
    value === 'error'
    ? value
    : fallback;
}

function asArguments(value: unknown): Record<string, unknown> {
  const parsed = parseJsonString(value);
  return asRecord(parsed) ?? {};
}

export function normalizeToolCallList(raw: unknown): ToolCall[] | undefined {
  const parsed = parseJsonString(raw);
  if (!Array.isArray(parsed)) return undefined;

  const calls = parsed
    .map((item, index): ToolCall | null => {
      const record = asRecord(item);
      if (!record) return null;

      const fn = asRecord(record.function);
      const id = typeof record.id === 'string' && record.id ? record.id : `tool-${index}`;
      const name =
        (typeof record.name === 'string' && record.name) ||
        (typeof fn?.name === 'string' && fn.name) ||
        'tool';

      return {
        id,
        name,
        arguments: asArguments(record.arguments ?? fn?.arguments),
        result: record.result,
        status: asStatus(record.status, 'success'),
        error: typeof record.error === 'string' ? record.error : undefined,
        duration_ms:
          typeof record.duration_ms === 'number' && Number.isFinite(record.duration_ms)
            ? record.duration_ms
            : undefined,
      };
    })
    .filter((item): item is ToolCall => item !== null);

  return calls.length > 0 ? calls : undefined;
}

function inferToolResultStatus(result: unknown): Pick<ToolCall, 'status' | 'error'> {
  const record = asRecord(result);
  if (!record) return { status: 'success' };

  const error = typeof record.error === 'string' ? record.error : undefined;
  if (error || record.success === false) {
    return { status: 'error', error };
  }
  return { status: 'success' };
}

function parseExtensionsRecord(extensions: MessageResponse['extensions']): UnknownRecord | null {
  if (extensions == null || extensions === '') return null;
  if (typeof extensions === 'object' && !Array.isArray(extensions)) {
    return extensions as UnknownRecord;
  }
  if (typeof extensions === 'string') {
    try {
      const p = JSON.parse(extensions) as unknown;
      return asRecord(p);
    } catch {
      return null;
    }
  }
  return null;
}

function normalizeTaskProgressFromExtensions(raw: unknown): TaskProgressStep[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  const out: TaskProgressStep[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const o = item as Record<string, unknown>;
    const tid = o.task_id != null ? String(o.task_id).trim() : '';
    const label = typeof o.label === 'string' ? o.label : '';
    const st = o.status;
    if (!tid || !label || typeof st !== 'string') continue;
    if (st !== 'pending' && st !== 'in_progress' && st !== 'completed' && st !== 'failed') continue;
    const step: TaskProgressStep = {
      taskId: tid,
      label,
      status: st,
    };
    if (typeof o.order === 'number' && Number.isFinite(o.order)) step.order = o.order;
    if (typeof o.progress === 'number' && Number.isFinite(o.progress)) step.progress = o.progress;
    out.push(step);
  }
  return out.length ? out : undefined;
}

function parseGenUiReplay(ext: UnknownRecord): Message['genUiReplay'] | undefined {
  const gu = ext.gen_ui;
  if (!gu || typeof gu !== 'object' || Array.isArray(gu)) return undefined;
  const g = gu as Record<string, unknown>;
  const tree = g.tree;
  if (!tree || typeof tree !== 'object' || Array.isArray(tree)) return undefined;
  if ((tree as Record<string, unknown>).schemaVersion !== '1') return undefined;
  return {
    tree: tree as GenUiTreeV1,
    tool_call_id: typeof g.tool_call_id === 'string' ? g.tool_call_id : undefined,
    canvas_id: typeof g.canvas_id === 'string' ? g.canvas_id : undefined,
  };
}

function parsePetBubbleFromExtensions(ext: UnknownRecord): PetBubblePayload | undefined {
  const pb = ext.pet_bubble;
  if (!pb || typeof pb !== 'object' || Array.isArray(pb)) return undefined;
  const o = pb as Record<string, unknown>;
  const text = typeof o.text === 'string' ? o.text.trim() : '';
  if (!text) return undefined;
  const out: PetBubblePayload = { text: text.slice(0, 120) };
  const em = o.emoji;
  if (typeof em === 'string' && em.trim()) {
    out.emoji = em.trim().slice(0, 16);
  }
  return out;
}

function applyToolResult(messages: Message[], row: MessageResponse): void {
  const toolCallId = row.tool_call_id || row.id;
  if (!toolCallId) return;

  const result = parseJsonString(row.content);
  const inferred = inferToolResultStatus(result);
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message?.role !== 'assistant') continue;

    const existing = message.toolCalls ?? [];
    const index = existing.findIndex((tc) => tc.id === toolCallId);
    if (index !== -1) {
      const nextToolCalls = [...existing];
      const prev = nextToolCalls[index];
      if (!prev) return;

      nextToolCalls[index] = {
        ...prev,
        result,
        status: inferred.status,
        error: inferred.error ?? prev.error,
      };
      messages[i] = { ...message, toolCalls: nextToolCalls };
      return;
    }

    // Legacy rows: assistant stored without tool_calls; attach a stub so results still render.
    if (existing.length === 0) {
      messages[i] = {
        ...message,
        toolCalls: [
          {
            id: toolCallId,
            name: 'tool',
            arguments: {},
            result,
            status: inferred.status,
            error: inferred.error,
          },
        ],
      };
      return;
    }
  }
}

function usageFromMessageRow(row: MessageResponse): Message['usage'] | undefined {
  if (row.role !== 'assistant') return undefined;
  const pt = row.input_tokens;
  const ct = row.output_tokens;
  const tt = row.total_tokens;
  const hasPrompt = typeof pt === 'number' && Number.isFinite(pt);
  const hasCompletion = typeof ct === 'number' && Number.isFinite(ct);
  const hasTotal = typeof tt === 'number' && Number.isFinite(tt);
  if (!hasPrompt && !hasCompletion && !hasTotal) return undefined;

  const prompt_tokens = hasPrompt ? pt : 0;
  const completion_tokens = hasCompletion ? ct : 0;
  const total_tokens = hasTotal ? tt : prompt_tokens + completion_tokens;

  return {
    prompt_tokens,
    completion_tokens,
    total_tokens,
  };
}

export function normalizeMessageList(rows: MessageResponse[]): Message[] {
  const messages: Message[] = [];

  for (const row of rows) {
    if (row.role === 'tool') {
      applyToolResult(messages, row);
      continue;
    }

    const workflow = parseWorkflowFromExtensions(row.extensions);
    const workflowEmbed = parseWorkflowEmbedFromExtensions(row.extensions);
    const extRec = parseExtensionsRecord(row.extensions);
    const thinkingPersisted =
      extRec && typeof extRec.thinking === 'string' && extRec.thinking.trim()
        ? extRec.thinking.trim()
        : undefined;
    const taskProgressPersisted = extRec ? normalizeTaskProgressFromExtensions(extRec.task_progress) : undefined;
    const genUiReplay = extRec ? parseGenUiReplay(extRec) : undefined;
    const petBubblePersisted = extRec ? parsePetBubbleFromExtensions(extRec) : undefined;
    const persistedUsage = usageFromMessageRow(row);

    messages.push({
      id: row.id,
      role: row.role,
      content: row.content,
      createdAt: row.created_at,
      ...(typeof row.rating === 'number' || row.rating === null ? { rating: row.rating } : {}),
      toolCalls: normalizeToolCallList(row.tool_calls),
      attachments: normalizeAttachmentList(row.attachments),
      ...(workflow ? { workflow } : {}),
      ...(workflowEmbed ? { workflowEmbed } : {}),
      ...(thinkingPersisted ? { thinking: thinkingPersisted } : {}),
      ...(taskProgressPersisted ? { taskProgress: taskProgressPersisted } : {}),
      ...(genUiReplay ? { genUiReplay } : {}),
      ...(petBubblePersisted ? { petBubble: petBubblePersisted } : {}),
      ...(persistedUsage ? { usage: persistedUsage } : {}),
    });
  }

  const seen = new Set<string>();
  return messages.filter((m) => {
    if (seen.has(m.id)) return false;
    seen.add(m.id);
    return true;
  });
}
