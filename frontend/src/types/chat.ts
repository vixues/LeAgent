import type { GenUiTreeV1 } from './genUi';

/** Live preview of sub-agent (coding_agent) tool args streamed over SSE — not persisted. */
export interface NestedAgentPreviewState {
  parentToolCallId: string;
  toolName: string;
  argumentsRaw: string;
  argumentsPartial?: Record<string, unknown>;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  /** Live JSON fragment while the model streams tool arguments (SSE tool_call_delta). */
  argumentsRaw?: string;
  /** Provider slot index — matches backend delta payloads before stable id exists. */
  toolCallIndex?: number;
  result?: unknown;
  status: 'pending' | 'running' | 'awaiting_user' | 'success' | 'error';
  error?: string;
  duration_ms?: number;
}

export type TaskProgressStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled';

export interface TaskProgressStep {
  taskId: string;
  label: string;
  status: TaskProgressStatus;
  order?: number;
  progress?: number;
}

export type ChatWorkflowStepRunState = 'idle' | 'running' | 'success' | 'error';

export interface ChatWorkflowStepRunRecord {
  status: ChatWorkflowStepRunState;
  error?: string;
  prompt_id?: string;
  run_id?: string;
}

export interface ChatWorkflowToolActionModel {
  kind: 'tool';
  tool_id: string;
  arguments: Record<string, unknown>;
}

export interface ChatWorkflowStepModel {
  id: string;
  label: string;
  hint?: string;
  action: ChatWorkflowToolActionModel;
}

export interface ChatWorkflowSpecModel {
  version: 1;
  title: string;
  summary?: string;
  steps: ChatWorkflowStepModel[];
}

export interface ChatWorkflowUiState {
  spec: ChatWorkflowSpecModel;
  digest: string;
  stepRuns: Record<string, ChatWorkflowStepRunRecord>;
}

/** Flow.data-shaped DAG persisted in extensions (same format as Flow editor). */
export interface ChatWorkflowEmbedState {
  data: Record<string, unknown>;
  digest: string;
  title?: string;
  summary?: string;
  flowId?: string;
}

/** Hydrate workflow card state from API `extensions` JSON (string or object). */
export function parseWorkflowFromExtensions(
  ext: unknown,
): ChatWorkflowUiState | undefined {
  if (ext == null || ext === '') return undefined;
  let obj: Record<string, unknown>;
  if (typeof ext === 'string') {
    try {
      obj = JSON.parse(ext) as Record<string, unknown>;
    } catch {
      return undefined;
    }
  } else if (typeof ext === 'object' && !Array.isArray(ext)) {
    obj = ext as Record<string, unknown>;
  } else {
    return undefined;
  }
  const spec = obj.chat_workflow;
  const digest = obj.chat_workflow_digest;
  if (!spec || typeof spec !== 'object' || typeof digest !== 'string' || !digest) {
    return undefined;
  }
  const s = spec as Partial<ChatWorkflowSpecModel>;
  if (typeof s.title !== 'string' || !Array.isArray(s.steps)) return undefined;

  const stepRuns: Record<string, ChatWorkflowStepRunRecord> = {};
  const rawRuns = obj.chat_workflow_step_runs;
  if (rawRuns && typeof rawRuns === 'object' && !Array.isArray(rawRuns)) {
    for (const [key, v] of Object.entries(rawRuns)) {
      if (!v || typeof v !== 'object' || Array.isArray(v)) continue;
      const st = (v as Record<string, unknown>).status;
      if (st === 'idle' || st === 'running' || st === 'success' || st === 'error') {
        const raw = v as Record<string, unknown>;
        let status = st;
        if (st === 'running') {
          const err = raw.error;
          const completedAt = raw.completed_at;
          if (typeof err === 'string' && err) {
            status = 'error';
          } else if (completedAt) {
            status = 'success';
          } else {
            // Sync chat steps cannot stay in-flight after reload (legacy rows).
            status = 'idle';
          }
        }
        const rec: ChatWorkflowStepRunRecord = { status };
        const err = raw.error;
        if (typeof err === 'string' && err) rec.error = err;
        const promptId = raw.prompt_id;
        if (typeof promptId === 'string' && promptId) rec.prompt_id = promptId;
        const runId = raw.run_id;
        if (typeof runId === 'string' && runId) rec.run_id = runId;
        stepRuns[key] = rec;
      }
    }
  }

  return {
    spec: s as ChatWorkflowSpecModel,
    digest,
    stepRuns,
  };
}

/** Hydrate embedded Flow-compatible workflow from `extensions`. */
export function parseWorkflowEmbedFromExtensions(ext: unknown): ChatWorkflowEmbedState | undefined {
  if (ext == null || ext === '') return undefined;
  let obj: Record<string, unknown>;
  if (typeof ext === 'string') {
    try {
      obj = JSON.parse(ext) as Record<string, unknown>;
    } catch {
      return undefined;
    }
  } else if (typeof ext === 'object' && !Array.isArray(ext)) {
    obj = ext as Record<string, unknown>;
  } else {
    return undefined;
  }
  const wrap = obj.workflow_embed;
  if (!wrap || typeof wrap !== 'object' || Array.isArray(wrap)) return undefined;
  const w = wrap as Record<string, unknown>;
  const data = w.data;
  const digest = w.digest ?? obj.workflow_embed_digest;
  if (!data || typeof data !== 'object' || Array.isArray(data)) return undefined;
  if (typeof digest !== 'string' || !digest.trim()) return undefined;
  const title = obj.workflow_embed_title;
  const summary = obj.workflow_embed_summary;
  const flowId = obj.workflow_embed_flow_id;
  return {
    data: data as Record<string, unknown>,
    digest: digest.trim(),
    title: typeof title === 'string' && title.trim() ? title.trim() : undefined,
    summary: typeof summary === 'string' && summary.trim() ? summary.trim() : undefined,
    flowId: typeof flowId === 'string' && flowId.trim() ? flowId.trim() : undefined,
  };
}

export interface MessageUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  reasoning_tokens?: number;
  /** DeepSeek KV cache (when provider returns usage). */
  prompt_cache_hit_tokens?: number;
  prompt_cache_miss_tokens?: number;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: string;
  /** 5 = thumbs up, 1 = thumbs down (matches backend ``Message.rating``). */
  rating?: number | null;
  toolCalls?: ToolCall[];
  taskProgress?: TaskProgressStep[];
  attachments?: Attachment[];
  isStreaming?: boolean;
  thinking?: string;
  /** Token usage statistics from the LLM response. */
  usage?: MessageUsage;
  /** Structured workflow card (streamed + persisted via `extensions`). */
  workflow?: ChatWorkflowUiState;
  /** Flow.data-shaped DAG (same as Flow editor / engine document + optional ui). */
  workflowEmbed?: ChatWorkflowEmbedState;
  /** Snapshot from ``Message.extensions.gen_ui``; hydrated into ``useGenUiStore`` when loading history. */
  genUiReplay?: { tree: GenUiTreeV1; tool_call_id?: string; canvas_id?: string };
  /** Assistant pet speech bubble from ``extensions.pet_bubble`` / SSE ``pet_bubble``. */
  petBubble?: PetBubblePayload;
}

/** Short text + optional emoji shown beside the chat mascot (agent-controlled). */
export interface PetBubblePayload {
  text: string;
  emoji?: string;
}

export interface Attachment {
  id: string;
  name: string;
  type: string;
  size: number;
  /** Legacy download URL. Prefer `downloadUrl` below. */
  url?: string;
  /**
   * Coarse category computed by the backend SessionManager
   * (image / document / code / data / audio / video / other).
   * Used by the composer / AttachmentCard to pick the right icon
   * and decide whether to show an inline preview.
   */
  kind?: string;
  /** Short-lived signed URL — safe to embed in <img src>. */
  previewUrl?: string;
  /** Short-lived signed URL for explicit downloads. */
  downloadUrl?: string;
  /** Resolved absolute path on the API host (desktop / local profile only). */
  localPath?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
  preview?: string;
  /** Server-backed pin order; message UUID strings from ``SessionRead.pinned_message_ids``. */
  pinnedMessageIds?: string[];
  /** Session-scoped agent todos (from SessionRead.todos / SSE session_todos). */
  todos?: TaskProgressStep[];
  /**
   * `true` while the optimistic temp UUID has not yet been swapped for a server-issued one.
   * Background queries (agent-memory, prompt-preview) skip these to avoid spurious 404s.
   */
  isPending?: boolean;
}

export interface ChatState {
  sessions: ChatSession[];
  currentSessionId: string | null;
  messages: Message[];
  isLoading: boolean;
  isStreaming: boolean;
  error: string | null;
}

export interface SendMessageParams {
  content: string;
  attachments?: File[];
  folderId?: string | null;
  /** Knowledge document UUIDs for ``/chat/stream`` ``file_ids`` (comma-separated on wire). */
  fileIds?: string[];
  /**
   * Folder bound to a code project (``Folder.is_project=true``). Sent
   * to the backend as ``project_folder_id`` so it can fold the
   * resolved on-disk path into ``tool_extra['project_roots']`` for
   * the coding agent and ``project_*`` tools.
   */
  projectFolderId?: string | null;
  /** Model mode from the composer selector (auto/fast/reasoning). */
  modelMode?: string;
}

export interface AuthorizedPathEntry {
  path: string;
  label?: string | null;
}

export interface AuthorizedPathsResponse {
  session_id: string;
  paths: AuthorizedPathEntry[];
}

export interface AuthorizedPathCreateBody {
  path: string;
  label?: string | null;
}

/** ``permission_kind`` when ``ui_variant`` is ``permission`` (icons / subtitle). */
export type UserInputPermissionKind =
  | 'file_access'
  | 'tool_run'
  | 'mode_change'
  | 'generic';

/** One question from the ``ask_user`` tool (SSE / UI). */
export interface UserInputQuestion {
  id: string;
  prompt: string;
  choices?: string[];
  allow_custom?: boolean;
  multi_select?: boolean;
  /** ``permission``: Cursor-style Allow/Deny strip; default questionnaire chips. */
  ui_variant?: 'questionnaire' | 'permission';
  permission_kind?: UserInputPermissionKind;
  /** Path, tool name, mode label — shown under the title for permission UI. */
  detail?: string;
  primary_choice?: string;
  secondary_choice?: string;
}

/** Pending ask_user questionnaire for the composer bar. */
export interface PendingUserInput {
  sessionId: string;
  assistantMsgId: string;
  toolCallId: string;
  questions: UserInputQuestion[];
  checkpointId?: string;
}

/**
 * Why the agent stopped. Mirrors backend `TerminalReason` (Python str enum).
 * Surfaced on the `assistant_complete` and `error` SSE events so the frontend
 * can show differentiated end-of-turn UI.
 */
export type TerminalReason =
  | 'completed'
  | 'max_turns'
  | 'blocking_limit'
  | 'model_error'
  | 'aborted_streaming'
  | 'prompt_too_long'
  | 'token_budget_exceeded'
  | 'awaiting_user_input';

export interface StreamEvent {
  type:
    | 'content'
    | 'tool_call'
    | 'tool_call_delta'
    | 'tool_result'
    | 'thinking'
    | 'error'
    | 'attachments'
    | 'workspace_attachments'
    | 'execution_started'
    | 'task_progress'
    | 'session_todos'
    | 'workflow'
    | 'workflow_done'
    | 'canvas'
    | 'ui_tree'
    | 'ui_patch'
    | 'pet_bubble'
    | 'user_input_request'
    | 'nested_agent_preview'
    | 'context_usage'
    | 'assistant_complete'
    | 'message_ids'
    | 'code_artifact'
    | 'agent_task'
    | 'done';
  data: unknown;
}

export interface TaskProgressEventPayload {
  task_id: string;
  label: string;
  status: TaskProgressStatus;
  order?: number;
  progress?: number;
}

export interface SessionTodosEventPayload {
  todos: Array<{
    id: string;
    content: string;
    status: TaskProgressStatus;
    order?: number;
  }>;
}

/**
 * Payload emitted by the backend `type: "attachments"` SSE event once the
 * SessionManager has persisted a batch of user uploads and built their
 * signed preview URLs. The frontend uses this to hydrate the pending user
 * message with real ids + thumbnails without waiting for the message list
 * refetch.
 */
export interface AttachmentEventPayload {
  session_id: string;
  attachments: Array<{
    id?: string;
    name?: string;
    filename?: string;
    kind?: string;
    type?: string;
    content_type?: string;
    size?: number;
    previewUrl?: string;
    preview_url?: string;
    downloadUrl?: string;
    download_url?: string;
    url?: string;
    localPath?: string;
    local_path?: string;
  }>;
}

type UnknownRecord = Record<string, unknown>;

function asRecord(value: unknown): UnknownRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as UnknownRecord;
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim().length > 0 ? value : undefined;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function defaultKindFromType(type: string | undefined): string | undefined {
  if (!type) return undefined;
  const ct = type.toLowerCase();
  if (ct.startsWith('image/')) return 'image';
  if (ct.startsWith('audio/')) return 'audio';
  if (ct.startsWith('video/')) return 'video';
  if (ct.startsWith('text/')) return 'document';
  return undefined;
}

export function normalizeAttachment(
  raw: unknown,
  fallbackId: string,
): Attachment | null {
  // Persisted chat rows often store `["<file-uuid>", …]` without metadata.
  if (typeof raw === 'string') {
    const id = raw.trim();
    if (!id) return null;
    return {
      id,
      name: 'attachment',
      type: '',
      size: 0,
    };
  }

  const record = asRecord(raw);
  if (!record) return null;

  const name =
    asString(record.name) ??
    asString(record.filename) ??
    asString(record.file_name) ??
    'attachment';
  const type =
    asString(record.type) ??
    asString(record.content_type) ??
    asString(record.mime_type) ??
    '';
  const previewUrl = asString(record.previewUrl) ?? asString(record.preview_url);
  const downloadUrl =
    asString(record.downloadUrl) ?? asString(record.download_url);
  const url = asString(record.url);
  const localPath =
    asString(record.localPath) ?? asString(record.local_path);
  const size = asNumber(record.size) ?? 0;
  const kind = asString(record.kind) ?? defaultKindFromType(type);

  return {
    id: asString(record.id) ?? fallbackId,
    name,
    type,
    size,
    kind,
    previewUrl,
    downloadUrl,
    url,
    ...(localPath ? { localPath } : {}),
  };
}

export function normalizeAttachmentList(raw: unknown): Attachment[] {
  let source = raw;
  if (typeof source === 'string') {
    try {
      source = JSON.parse(source);
    } catch {
      return [];
    }
  }

  if (!Array.isArray(source)) return [];

  return source
    .map((item, index) => normalizeAttachment(item, `attachment-${index}`))
    .filter((item): item is Attachment => !!item);
}
