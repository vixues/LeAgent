/**
 * Typed dispatcher that turns a GenUi `Button` / `InteractiveButton` /
 * `ToggleButton` click into a real system action (chat send, artifact open,
 * url open, navigation, ui patch).
 *
 * The renderer must stay decoupled from `react-router` and the chat store, so
 * we use a small singleton that the chat shell wires up via
 * `<GenUiActionBridge />`.
 */

import type { UiPatchStreamPayload } from '@/types/genUi';
import { isSafeHref } from '@/lib/genUiUrl';

export type GenUiActionType =
  | 'send_message'
  | 'open_url'
  | 'open_artifact'
  | 'open_file'
  | 'navigate'
  | 'patch_ui'
  | 'submit_form'
  | 'run_workflow'
  | 'resume_workflow';

export interface SendMessageActionPayload {
  content: string;
  attachments?: string[];
}

export interface OpenUrlActionPayload {
  url: string;
  external?: boolean;
}

export interface OpenArtifactActionPayload {
  messageId?: string;
  canvasId?: string;
  artifactId?: string;
}

export interface OpenFileActionPayload {
  fileId: string;
}

export interface NavigateActionPayload {
  route: string;
}

export interface PatchUiActionPayload {
  patches: UiPatchStreamPayload['patches'];
  /** When omitted, the dispatcher uses the active tree from the dispatching button context. */
  sessionId?: string;
  messageId?: string;
}

export interface SubmitFormActionPayload {
  formId?: string;
  /** Collected named field values from the enclosing GenUi Form. */
  values: Record<string, unknown>;
}

/**
 * Where a ``run_workflow`` action should be dispatched. Defaults to ``flow``
 * (the saved-Flow run API). Chat surfaces route to the verified chat endpoints
 * so digest verification + per-message run persistence still apply.
 */
export type WorkflowRunTarget =
  | { kind: 'flow' }
  | { kind: 'chat_embed'; sessionId: string; messageId: string; digest: string }
  | { kind: 'chat_step'; sessionId: string; messageId: string; digest: string; stepId?: string };

export interface RunWorkflowActionPayload {
  /** Saved Flow id. Empty for unsaved chat embeds (use ``target`` instead). */
  flowId: string;
  /** Workflow input values (from the enclosing Form unless inlined). */
  values: Record<string, unknown>;
  /** Routing target; absent payloads behave as ``{ kind: 'flow' }``. */
  target?: WorkflowRunTarget;
}

export interface ResumeWorkflowActionPayload {
  promptId: string;
  /** Resume data (e.g. `{answer}` or `{approved, comments}`) merged with form values. */
  values: Record<string, unknown>;
}

export type GenUiAction =
  | { type: 'send_message'; payload: SendMessageActionPayload }
  | { type: 'open_url'; payload: OpenUrlActionPayload }
  | { type: 'open_artifact'; payload: OpenArtifactActionPayload }
  | { type: 'open_file'; payload: OpenFileActionPayload }
  | { type: 'navigate'; payload: NavigateActionPayload }
  | { type: 'patch_ui'; payload: PatchUiActionPayload }
  | { type: 'submit_form'; payload: SubmitFormActionPayload }
  | { type: 'run_workflow'; payload: RunWorkflowActionPayload }
  | { type: 'resume_workflow'; payload: ResumeWorkflowActionPayload };

/** Minimal context describing where the action came from (used as fallback). */
export interface GenUiActionContext {
  sessionId?: string;
  messageId?: string;
  /** Original `actionId` passed by the model — used as fallback chat content. */
  actionId?: string;
  /** Toggle state delta for ToggleButton. */
  toggled?: boolean;
  /** Named field values from the enclosing GenUi Form (set by form-aware buttons). */
  formValues?: Record<string, unknown>;
  /** The enclosing Form's id (set by form-aware buttons). */
  formId?: string;
}

export interface GenUiActionAdapters {
  sendMessage?: (p: SendMessageActionPayload, ctx: GenUiActionContext) => void | Promise<void>;
  openUrl?: (p: OpenUrlActionPayload, ctx: GenUiActionContext) => void;
  openArtifact?: (p: OpenArtifactActionPayload, ctx: GenUiActionContext) => void;
  openFile?: (p: OpenFileActionPayload, ctx: GenUiActionContext) => void;
  navigate?: (p: NavigateActionPayload, ctx: GenUiActionContext) => void;
  patchUi?: (p: PatchUiActionPayload, ctx: GenUiActionContext) => void;
  submitForm?: (p: SubmitFormActionPayload, ctx: GenUiActionContext) => void | Promise<void>;
  runWorkflow?: (p: RunWorkflowActionPayload, ctx: GenUiActionContext) => void | Promise<void>;
  resumeWorkflow?: (p: ResumeWorkflowActionPayload, ctx: GenUiActionContext) => void | Promise<void>;
}

let adapters: GenUiActionAdapters = {};

/** Wire adapters from the chat shell (idempotent). */
export function registerGenUiActionAdapters(next: GenUiActionAdapters): void {
  adapters = { ...adapters, ...next };
}

/** Reset adapters (test helper). */
export function resetGenUiActionAdapters(): void {
  adapters = {};
}

function isUiPatchArray(value: unknown): value is UiPatchStreamPayload['patches'] {
  return Array.isArray(value) && value.every((p) => p && typeof p === 'object' && 'op' in p && 'path' in p);
}

/** Inline payload values win over collected form values. */
function mergeFormValues(
  inline: unknown,
  ctx: GenUiActionContext,
): Record<string, unknown> {
  const fromForm = ctx.formValues ?? {};
  const fromInline =
    inline && typeof inline === 'object' && !Array.isArray(inline)
      ? (inline as Record<string, unknown>)
      : {};
  return { ...fromForm, ...fromInline };
}

/** Validate a loose ``run_workflow`` target discriminator. */
function parseRunTarget(raw: unknown): WorkflowRunTarget | undefined {
  if (!raw || typeof raw !== 'object') return undefined;
  const o = raw as Record<string, unknown>;
  const kind = o.kind;
  const str = (v: unknown): string => (typeof v === 'string' ? v : '');
  if (kind === 'flow') return { kind: 'flow' };
  if (kind === 'chat_embed') {
    const sessionId = str(o.sessionId);
    const messageId = str(o.messageId);
    const digest = str(o.digest);
    if (!sessionId || !messageId || !digest) return undefined;
    return { kind: 'chat_embed', sessionId, messageId, digest };
  }
  if (kind === 'chat_step') {
    const sessionId = str(o.sessionId);
    const messageId = str(o.messageId);
    const digest = str(o.digest);
    if (!sessionId || !messageId || !digest) return undefined;
    const stepId = str(o.stepId);
    return { kind: 'chat_step', sessionId, messageId, digest, ...(stepId ? { stepId } : {}) };
  }
  return undefined;
}

/**
 * Coerce loose model output into a strongly-typed action.
 * Accepts either a fully-typed `{type, payload}` object or a bare `actionId`
 * string — the latter falls back to a chat send_message.
 */
export function normalizeAction(
  raw: unknown,
  ctx: GenUiActionContext = {},
): GenUiAction | null {
  if (raw && typeof raw === 'object') {
    const obj = raw as Record<string, unknown>;
    const type = obj.type;
    const payload = (obj.payload ?? {}) as Record<string, unknown>;
    switch (type) {
      case 'send_message': {
        const content =
          typeof payload.content === 'string'
            ? payload.content
            : typeof obj.content === 'string'
              ? (obj.content as string)
              : ctx.actionId ?? '';
        if (!content.trim()) return null;
        const attachments = Array.isArray(payload.attachments)
          ? (payload.attachments.filter((a) => typeof a === 'string') as string[])
          : undefined;
        return { type: 'send_message', payload: { content, attachments } };
      }
      case 'open_url': {
        const url = typeof payload.url === 'string' ? payload.url : '';
        if (!isSafeHref(url)) return null;
        return { type: 'open_url', payload: { url, external: Boolean(payload.external) } };
      }
      case 'open_artifact': {
        return {
          type: 'open_artifact',
          payload: {
            messageId: typeof payload.messageId === 'string' ? payload.messageId : ctx.messageId,
            canvasId: typeof payload.canvasId === 'string' ? payload.canvasId : undefined,
            artifactId: typeof payload.artifactId === 'string' ? payload.artifactId : undefined,
          },
        };
      }
      case 'open_file': {
        const fileId = typeof payload.fileId === 'string' ? payload.fileId : '';
        if (!fileId) return null;
        return { type: 'open_file', payload: { fileId } };
      }
      case 'navigate': {
        const route = typeof payload.route === 'string' ? payload.route : '';
        if (!route) return null;
        return { type: 'navigate', payload: { route } };
      }
      case 'patch_ui': {
        const patches = isUiPatchArray(payload.patches) ? payload.patches : [];
        if (!patches.length) return null;
        return {
          type: 'patch_ui',
          payload: {
            patches,
            sessionId: typeof payload.sessionId === 'string' ? payload.sessionId : ctx.sessionId,
            messageId: typeof payload.messageId === 'string' ? payload.messageId : ctx.messageId,
          },
        };
      }
      case 'submit_form': {
        return {
          type: 'submit_form',
          payload: {
            formId: typeof payload.formId === 'string' ? payload.formId : ctx.formId,
            values: mergeFormValues(payload.values, ctx),
          },
        };
      }
      case 'run_workflow': {
        const flowId = typeof payload.flowId === 'string' ? payload.flowId : '';
        const target = parseRunTarget(payload.target);
        if (!flowId && !target) return null;
        return {
          type: 'run_workflow',
          payload: {
            flowId,
            values: mergeFormValues(payload.values, ctx),
            ...(target ? { target } : {}),
          },
        };
      }
      case 'resume_workflow': {
        const promptId = typeof payload.promptId === 'string' ? payload.promptId : '';
        if (!promptId) return null;
        return {
          type: 'resume_workflow',
          payload: { promptId, values: mergeFormValues(payload.values, ctx) },
        };
      }
      default:
        break;
    }
  }
  // Bare actionId fallback → send the actionId as a chat message
  const fallback = typeof raw === 'string' ? raw : ctx.actionId;
  if (typeof fallback === 'string' && fallback.trim().length > 0) {
    return {
      type: 'send_message',
      payload: { content: fallback.trim() },
    };
  }
  return null;
}

/**
 * Dispatch a GenUi action through registered adapters. Falls back to safe
 * defaults (e.g. window.open for unknown adapters) and is a no-op when no
 * action could be parsed.
 */
export function dispatchGenUiAction(raw: unknown, ctx: GenUiActionContext = {}): void {
  const action = normalizeAction(raw, ctx);
  if (!action) return;

  switch (action.type) {
    case 'send_message': {
      if (adapters.sendMessage) {
        void adapters.sendMessage(action.payload, ctx);
      }
      break;
    }
    case 'open_url': {
      if (adapters.openUrl) {
        adapters.openUrl(action.payload, ctx);
      } else if (typeof window !== 'undefined') {
        const target = action.payload.external ? '_blank' : '_self';
        window.open(action.payload.url, target, 'noopener,noreferrer');
      }
      break;
    }
    case 'open_artifact': {
      adapters.openArtifact?.(action.payload, ctx);
      break;
    }
    case 'open_file': {
      adapters.openFile?.(action.payload, ctx);
      break;
    }
    case 'navigate': {
      if (adapters.navigate) {
        adapters.navigate(action.payload, ctx);
      } else if (typeof window !== 'undefined') {
        window.location.href = action.payload.route;
      }
      break;
    }
    case 'patch_ui': {
      adapters.patchUi?.(action.payload, ctx);
      break;
    }
    case 'submit_form': {
      void adapters.submitForm?.(action.payload, ctx);
      break;
    }
    case 'run_workflow': {
      void adapters.runWorkflow?.(action.payload, ctx);
      break;
    }
    case 'resume_workflow': {
      void adapters.resumeWorkflow?.(action.payload, ctx);
      break;
    }
  }
}
