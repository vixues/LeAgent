import type { Attachment } from '@/types/chat';

/** Resolved path or filename used in workflow `${user_input}` / file inputs. */
export function attachmentPath(att: Attachment): string {
  if (att.localPath?.trim()) return att.localPath.trim();
  return att.name;
}

export function dedupeAttachments(attachments: Attachment[]): Attachment[] {
  const seen = new Set<string>();
  const out: Attachment[] = [];
  for (const att of attachments) {
    if (!att.id || seen.has(att.id)) continue;
    seen.add(att.id);
    out.push(att);
  }
  return out;
}

export function attachmentLabel(att: Attachment): string {
  return att.name?.trim() || att.id;
}

export function isImageAttachment(att: Attachment): boolean {
  const mime = att.type ?? '';
  return mime.startsWith('image/');
}
