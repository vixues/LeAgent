import type { ChatWorkflowStepModel } from '@/types/chat';

const FILE_PATH_TOOLS = new Set([
  'pdf_reader',
  'pdf',
  'read_pdf',
  'pdf_extract',
  'pdf_processor',
  'word_reader',
  'excel_reader',
  'image_ocr',
  'csv_processor',
  'html_processor',
  'markdown_processor',
  'doc_classifier',
]);

function argumentsNeedUserInput(args: Record<string, unknown>): boolean {
  const visit = (value: unknown): boolean => {
    if (typeof value === 'string') {
      return value.includes('${user_input}');
    }
    if (Array.isArray(value)) {
      return value.some(visit);
    }
    if (value && typeof value === 'object') {
      return Object.values(value as Record<string, unknown>).some(visit);
    }
    return false;
  };
  return visit(args);
}

/** Whether a step likely needs a user file path or optional-input filename. */
export function stepNeedsFileInput(step: ChatWorkflowStepModel): boolean {
  const toolId = step.action.tool_id;
  const args = step.action.arguments ?? {};
  if (FILE_PATH_TOOLS.has(toolId)) {
    return true;
  }
  if (Object.prototype.hasOwnProperty.call(args, 'file_path')) {
    const fp = args.file_path;
    if (fp == null || (typeof fp === 'string' && !fp.trim())) {
      return true;
    }
  }
  return argumentsNeedUserInput(args);
}

export function workflowNeedsFileInput(steps: ChatWorkflowStepModel[]): boolean {
  return steps.some(stepNeedsFileInput);
}
