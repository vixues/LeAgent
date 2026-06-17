import { useChatDraftStore } from '@/stores/chatDraft';
import type { PdfReaderTarget } from './types';

/** Build the `@file:name#id` reference token the backend resolves to a path. */
export function paperRefToken(target: PdfReaderTarget): string {
  const safeName = target.fileName.replace(/\s+/g, '_');
  return `@file:${safeName}#${target.fileId}`;
}

/** Ensure the open paper is attached as a composer reference exactly once. */
export function ensurePaperReferenced(target: PdfReaderTarget): void {
  const store = useChatDraftStore.getState();
  const token = paperRefToken(target);
  if (store.composerFileRefs.some((r) => r.token === token)) return;
  store.pushFileRef({ kind: 'workspace', token, label: target.fileName });
}

/** Insert a block-quote of selected PDF text into the composer. */
export function insertQuote(text: string, page?: number): void {
  const trimmed = text.trim();
  if (!trimmed) return;
  const cite = page ? ` (p.${page})` : '';
  const quoted = trimmed
    .split('\n')
    .map((line) => `> ${line}`)
    .join('\n');
  useChatDraftStore.getState().pushInsert(`${quoted}${cite}`);
}

/** Push a raw prompt line (e.g. an "Explain this" instruction) to the composer. */
export function appendPrompt(text: string): void {
  const trimmed = text.trim();
  if (!trimmed) return;
  useChatDraftStore.getState().pushInsert(trimmed);
}

/** Insert an "explain" instruction followed by the quoted passage. */
export function insertExplain(prompt: string, quote: string, page?: number): void {
  const trimmedQuote = quote.trim();
  const cite = page ? ` (p.${page})` : '';
  const quoted = trimmedQuote
    ? trimmedQuote
        .split('\n')
        .map((line) => `> ${line}`)
        .join('\n')
    : '';
  const body = quoted ? `${prompt.trim()}\n\n${quoted}${cite}` : prompt.trim();
  useChatDraftStore.getState().pushInsert(body);
}

/** Focus the chat composer so the user can type / send immediately. */
export function focusComposer(delayMs = 50): void {
  window.setTimeout(() => {
    document
      .querySelector<HTMLTextAreaElement>('textarea[data-composer-input]')
      ?.focus();
  }, delayMs);
}

/** Copy plain text to the clipboard. Returns success. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** Copy an image blob to the clipboard (best-effort; not all browsers allow it). */
export async function copyImage(blob: Blob): Promise<boolean> {
  try {
    const ClipboardItemCtor = (window as unknown as {
      ClipboardItem?: typeof ClipboardItem;
    }).ClipboardItem;
    if (!ClipboardItemCtor || !navigator.clipboard?.write) return false;
    await navigator.clipboard.write([new ClipboardItemCtor({ [blob.type]: blob })]);
    return true;
  } catch {
    return false;
  }
}

/** Stage an image (screenshot / cropped region) onto the composer. */
export function attachImage(file: File): void {
  useChatDraftStore.getState().setComposerFiles((prev) => [...prev, file]);
}

/** Convert a canvas region to a PNG File for composer attachment. */
export async function canvasRegionToFile(
  source: HTMLCanvasElement,
  rect: { x: number; y: number; width: number; height: number },
  fileName: string,
): Promise<File | null> {
  const w = Math.max(1, Math.round(rect.width));
  const h = Math.max(1, Math.round(rect.height));
  const out = document.createElement('canvas');
  out.width = w;
  out.height = h;
  const ctx = out.getContext('2d');
  if (!ctx) return null;
  ctx.drawImage(
    source,
    Math.round(rect.x),
    Math.round(rect.y),
    w,
    h,
    0,
    0,
    w,
    h,
  );
  return await canvasToFile(out, fileName);
}

export async function canvasToFile(
  canvas: HTMLCanvasElement,
  fileName: string,
): Promise<File | null> {
  return new Promise((resolve) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        resolve(null);
        return;
      }
      resolve(new File([blob], fileName, { type: 'image/png' }));
    }, 'image/png');
  });
}
