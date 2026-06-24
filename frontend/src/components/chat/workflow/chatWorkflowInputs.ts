/**
 * Builds the declarative input specs that drive the unified GenUI operation
 * panel for chat workflow cards.
 *
 * - DAG embeds reuse the document-level ``inputs`` array when present.
 * - Otherwise (and for linear step cards) we synthesize a single optional
 *   ``user_input`` field. Session attachments become ``choices`` so the
 *   click-to-fill UX from the legacy panel is preserved (renders a Select);
 *   free text remains available when no attachments exist.
 */

import { useShallow } from 'zustand/react/shallow';

import type { WorkflowInputSpec } from '@/features/workflow/genui/inputsToGenUiTree';
import { useChatStore } from '@/stores/chat';
import type { Attachment } from '@/types/chat';

/** The single placeholder field name consumed by ``${user_input}``. */
export const CHAT_USER_INPUT_FIELD = 'user_input';

export function attachmentPath(att: Attachment): string {
  if (att.localPath?.trim()) return att.localPath.trim();
  return att.name;
}

/** Deduped attachments across all messages in a chat session. */
export function useSessionAttachments(sessionId: string): Attachment[] {
  return useChatStore(
    useShallow((s) => {
      const messages = s.messages[sessionId] ?? [];
      const seen = new Set<string>();
      const out: Attachment[] = [];
      for (const msg of messages) {
        for (const att of msg.attachments ?? []) {
          if (!att.id || seen.has(att.id)) continue;
          seen.add(att.id);
          out.push(att);
        }
      }
      return out;
    }),
  );
}

export interface SynthesizedInputOptions {
  attachments: Attachment[];
  needsFileInput: boolean;
  label: string;
  description?: string;
}

/** A single optional ``user_input`` field, with attachments as quick-pick choices. */
export function synthesizedUserInputSpec(opts: SynthesizedInputOptions): WorkflowInputSpec {
  const paths = opts.attachments.map(attachmentPath).filter((p): p is string => Boolean(p));
  const base: WorkflowInputSpec = {
    name: CHAT_USER_INPUT_FIELD,
    label: opts.label,
    description: opts.description,
    required: false,
  };
  if (paths.length > 0) {
    // Distinct paths, preserving order.
    const choices = Array.from(new Set(paths));
    return { ...base, type: 'string', choices };
  }
  return { ...base, type: opts.needsFileInput ? 'file' : 'string' };
}

function isValidSpec(value: unknown): value is WorkflowInputSpec {
  return (
    Boolean(value) &&
    typeof value === 'object' &&
    typeof (value as { name?: unknown }).name === 'string' &&
    Boolean((value as { name?: unknown }).name)
  );
}

/**
 * Resolve the input specs for a DAG embed: declared ``data.inputs`` when
 * present, otherwise the synthesized ``user_input`` fallback.
 */
export function embedInputSpecs(
  data: Record<string, unknown> | undefined | null,
  fallback: WorkflowInputSpec,
): WorkflowInputSpec[] {
  const raw = data?.inputs;
  if (Array.isArray(raw)) {
    const specs = raw.filter(isValidSpec);
    if (specs.length > 0) return specs;
  }
  return [fallback];
}
