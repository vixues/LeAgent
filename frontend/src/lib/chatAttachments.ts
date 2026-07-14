import { apiClient } from '@/api/client';
import type { Message } from '@/types/chat';
import { normalizeAttachment } from '@/types/chat';

const INTERNAL_ATTACHMENT_NAMES = new Set(['__last_source__.py']);

/** Hide runtime state and keep only the latest card for each logical file. */
export function selectVisibleMessageAttachments(
  attachments: Message['attachments'],
): NonNullable<Message['attachments']> {
  if (!attachments?.length) return [];

  const byKey = new Map<string, NonNullable<Message['attachments']>[number]>();
  for (const attachment of attachments) {
    const name = attachment.name.trim();
    if (INTERNAL_ATTACHMENT_NAMES.has(name.toLowerCase())) continue;
    const key =
      name && name !== 'attachment'
        ? `name:${name.toLowerCase()}`
        : `id:${attachment.id}`;
    // Stream and persistence order are chronological, so replacement retains
    // the newest managed-file identity for repeated overwrites.
    byKey.set(key, attachment);
  }
  return Array.from(byKey.values());
}

/**
 * After GET /chat/sessions/:id/messages, user rows often store attachment **IDs**
 * only (`["uuid", …]`). Merge the catalog from GET /sessions/:id/attachments so
 * `AttachmentCard` receives filenames and signed preview/download URLs.
 */
export async function enrichMessagesWithSessionAttachments(
  sessionId: string,
  messages: Message[],
): Promise<Message[]> {
  const hasAny = messages.some((m) => (m.attachments?.length ?? 0) > 0);
  if (!hasAny) return messages;

  try {
    const res = await apiClient.get<{ attachments: unknown[] }>(
      `/chat/sessions/${sessionId}/attachments`,
    );
    const catalog = new Map<string, NonNullable<ReturnType<typeof normalizeAttachment>>>();
    const rawList = res.attachments ?? [];
    for (let i = 0; i < rawList.length; i++) {
      const att = normalizeAttachment(rawList[i], `session-att-${i}`);
      if (att?.id) catalog.set(att.id, att);
    }

    return messages.map((m) => {
      if (!m.attachments?.length) return m;
      const merged = m.attachments.map((a) => {
        const rich = catalog.get(a.id);
        if (!rich) return a;
        return {
          ...a,
          name:
            a.name && a.name !== 'attachment' ? a.name : rich.name || a.name,
          type: rich.type || a.type,
          size: rich.size ?? a.size,
          kind: rich.kind ?? a.kind,
          previewUrl: rich.previewUrl ?? a.previewUrl,
          downloadUrl: rich.downloadUrl ?? a.downloadUrl,
          url: rich.url ?? a.url,
          localPath: rich.localPath ?? a.localPath,
        };
      });
      return { ...m, attachments: merged };
    });
  } catch {
    return messages;
  }
}
