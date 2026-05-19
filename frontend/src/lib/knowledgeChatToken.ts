import type { ComposerFileRef } from '@/stores/chatDraft';

/** Build a single-line @knowledge token for the chat API (resolved by file UUID). */
export function buildKnowledgeChatToken(originalName: string, fileId: string): string {
  const trimmed = originalName.trim() || 'document';
  const safe =
    trimmed.replace(/[@#\r\n]/g, '_').replace(/\s+/g, '_').trim() || 'document';
  return `@knowledge:${safe}#${fileId}`;
}

const KNOWLEDGE_UUID_IN_TOKEN =
  /@knowledge:[^#]*#([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/i;

/** UUIDs from knowledge composer chips for the ``file_ids`` form field. */
export function knowledgeFileIdsFromComposerRefs(refs: ComposerFileRef[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const r of refs) {
    if (r.kind !== 'knowledge') continue;
    const m = r.token.match(KNOWLEDGE_UUID_IN_TOKEN);
    if (!m?.[1]) continue;
    const id = m[1].toLowerCase();
    if (seen.has(id)) continue;
    seen.add(id);
    out.push(m[1]);
  }
  return out;
}
