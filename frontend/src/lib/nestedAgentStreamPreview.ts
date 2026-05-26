import { pickCodeExecutionSourcePreview } from '@/lib/codeExecutionStreamPreview';
import {
  extractDocProcessorPreviewText,
  isDocProcessorTool,
} from '@/lib/docProcessorStreamPreview';
import { pickJsonStringField } from '@/lib/jsonStreamField';
import { extToLanguage } from '@/pages/FolderPage/project/extToLanguage';

/**
 * Best-effort text to show in the nested coding-agent live preview card.
 */
export function extractNestedPreviewText(
  toolName: string,
  argumentsRaw: string,
  argumentsPartial?: Record<string, unknown>,
): string {
  if (toolName === 'code_execution') {
    return pickCodeExecutionSourcePreview(argumentsRaw, argumentsPartial);
  }
  if (toolName === 'project_write') {
    return pickJsonStringField('content', argumentsRaw, argumentsPartial);
  }
  if (toolName === 'project_edit') {
    return pickJsonStringField('new_string', argumentsRaw, argumentsPartial);
  }
  if (toolName === 'project_apply_patch') {
    return pickJsonStringField('diff', argumentsRaw, argumentsPartial);
  }
  if (isDocProcessorTool(toolName)) {
    return extractDocProcessorPreviewText(toolName, argumentsRaw, argumentsPartial);
  }
  return argumentsRaw.length > 12000 ? `${argumentsRaw.slice(0, 12000)}\n…` : argumentsRaw;
}

export function languageForNestedPreview(
  toolName: string,
  argumentsPartial?: Record<string, unknown>,
): string {
  if (toolName === 'code_execution') return 'python';
  if (toolName === 'project_apply_patch') return 'diff';
  if (toolName === 'markdown_processor') return 'markdown';
  const p = argumentsPartial?.path ?? argumentsPartial?.file_path;
  if (typeof p === 'string' && p.length > 0) {
    return extToLanguage(p);
  }
  return 'text';
}
