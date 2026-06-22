import type { Message } from '@/types/chat';

/**
 * Type-aware first-paint height estimate for a chat row (px), including the
 * inter-row gap. These only seed the spacer before a row is measured; the
 * ResizeObserver pipeline replaces them with real heights as rows mount.
 */
const LINE_HEIGHT = 26;
const CHARS_PER_LINE = 78;
const ROW_GAP = 32; // matches pb-8 on the virtual row wrapper
const ROLE_LABEL = 28;

function textLines(content: string | undefined): number {
  const len = content?.length ?? 0;
  if (len === 0) return 0;
  // Count explicit newlines plus wrapped lines.
  const newlineCount = (content!.match(/\n/g)?.length ?? 0) + 1;
  const wrapped = Math.ceil(len / CHARS_PER_LINE);
  return Math.max(newlineCount, wrapped);
}

export function estimateRowHeight(message: Message): number {
  if (message.role === 'user') {
    let h = ROLE_LABEL + 16;
    h += Math.max(1, textLines(message.content)) * LINE_HEIGHT + 20;
    if (message.attachments?.length) h += 92;
    return h + ROW_GAP;
  }

  // assistant / system
  let h = ROLE_LABEL + 12;
  h += textLines(message.content) * LINE_HEIGHT;

  // Fenced code blocks are tall; each pair of ``` fences ~= one block.
  const fenceCount = message.content ? message.content.match(/```/g)?.length ?? 0 : 0;
  h += Math.floor(fenceCount / 2) * 160;

  if (message.thinking) h += 44;
  if (message.toolCalls?.length) h += 48 + message.toolCalls.length * 6;
  if (message.taskProgress?.length) h += 40 + message.taskProgress.length * 24;
  if (message.attachments?.length || message.inlineMedia?.length) h += 220;
  if (message.workflow || message.workflowEmbed) h += 160;
  if (!message.content && message.isStreaming) h += 36;

  return Math.max(h, 60) + ROW_GAP;
}
