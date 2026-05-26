import { pickJsonStringField, pickJsonStringOperation } from '@/lib/jsonStreamField';
import { extToLanguage } from '@/pages/FolderPage/project/extToLanguage';
import type { Message, ToolCall } from '@/types/chat';

export const TEXT_PROCESSOR = 'text_processor';
export const MARKDOWN_PROCESSOR = 'markdown_processor';

const WRITE_CONTENT_KEYS: Record<string, string> = {
  [TEXT_PROCESSOR]: 'data',
  [MARKDOWN_PROCESSOR]: 'content',
};

const WRITE_OPERATIONS = new Set([
  'write',
  'append',
  'prepend',
  'create',
  'insert_section',
]);

export function isDocProcessorTool(name: string): boolean {
  return name === TEXT_PROCESSOR || name === MARKDOWN_PROCESSOR;
}

export function isDocProcessorWriteStream(
  toolName: string,
  argumentsRaw: string,
  argumentsPartial?: Record<string, unknown>,
): boolean {
  if (!isDocProcessorTool(toolName)) return false;
  const op = pickJsonStringOperation(argumentsRaw, argumentsPartial);
  return WRITE_OPERATIONS.has(op);
}

export function extractDocProcessorPreviewText(
  toolName: string,
  argumentsRaw: string,
  argumentsPartial?: Record<string, unknown>,
): string {
  const contentKey = WRITE_CONTENT_KEYS[toolName];
  if (!contentKey) {
    return argumentsRaw.length > 12000 ? `${argumentsRaw.slice(0, 12000)}\n…` : argumentsRaw;
  }
  return pickJsonStringField(contentKey, argumentsRaw, argumentsPartial);
}

export function extractDocProcessorPath(
  argumentsRaw: string,
  argumentsPartial?: Record<string, unknown>,
): string {
  return pickJsonStringField('file_path', argumentsRaw, argumentsPartial).trim();
}

export function languageForDocProcessorPreview(
  filePath: string,
  toolName: string,
): string {
  if (toolName === MARKDOWN_PROCESSOR) return 'markdown';
  if (filePath) return extToLanguage(filePath);
  return 'text';
}

export interface ActiveDocProcessorStream {
  toolCall: ToolCall;
  toolName: string;
  filePath: string;
  previewText: string;
  language: string;
}

/**
 * Newest in-flight ``text_processor`` / ``markdown_processor`` write whose
 * arguments are still streaming (``argumentsRaw`` present).
 */
export function findActiveDocProcessorStream(
  messages: Message[],
): ActiveDocProcessorStream | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (m?.role !== 'assistant') continue;
    const tcs = m.toolCalls ?? [];
    for (let j = tcs.length - 1; j >= 0; j -= 1) {
      const tc = tcs[j];
      if (!tc || !isDocProcessorTool(tc.name)) continue;
      if (tc.status !== 'running' && tc.status !== 'pending') continue;
      const raw = typeof tc.argumentsRaw === 'string' ? tc.argumentsRaw : '';
      const partial =
        tc.arguments && typeof tc.arguments === 'object'
          ? (tc.arguments as Record<string, unknown>)
          : undefined;
      if (!raw && !partial) continue;
      if (!isDocProcessorWriteStream(tc.name, raw, partial)) continue;
      const filePath =
        extractDocProcessorPath(raw, partial) ||
        (typeof partial?.file_path === 'string' ? partial.file_path : '');
      const previewText = extractDocProcessorPreviewText(tc.name, raw, partial);
      return {
        toolCall: tc,
        toolName: tc.name,
        filePath,
        previewText,
        language: languageForDocProcessorPreview(filePath, tc.name),
      };
    }
  }
  return null;
}
