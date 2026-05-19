import type { Message } from '@/types/chat';

export interface AgentImageArtifact {
  id: string;
  mime: string;
  fileName?: string;
  previewUrl: string;
  downloadUrl?: string;
  sha256?: string;
}

/**
 * Collect generated code-execution images from managed artifacts only.
 * Historical inline base64 payloads are intentionally ignored.
 */
export function collectAgentImageArtifacts(messages: Message[]): AgentImageArtifact[] {
  const out: AgentImageArtifact[] = [];
  const seen = new Set<string>();

  for (const m of messages) {
    if (m.role !== 'assistant' || !m.toolCalls?.length) continue;
    for (const tc of m.toolCalls) {
      if (!tc || tc.name !== 'code_execution') continue;
      if (tc.status !== 'success' && tc.status !== 'error') continue;

      const result = tc.result;
      if (!result || typeof result !== 'object' || Array.isArray(result)) continue;
      const artifacts = (result as Record<string, unknown>).managed_artifacts;
      if (!Array.isArray(artifacts)) continue;

      for (const raw of artifacts) {
        if (!raw || typeof raw !== 'object') continue;
        const entry = raw as Record<string, unknown>;
        const mime = asString(entry.content_type) ?? asString(entry.mime) ?? '';
        if (!mime.toLowerCase().startsWith('image/')) continue;
        const previewUrl = asString(entry.preview_url) ?? asString(entry.previewUrl);
        if (!previewUrl) continue;
        const id = asString(entry.id) ?? `${m.id}-${tc.id}-${previewUrl}`;
        if (seen.has(id)) continue;
        seen.add(id);
        out.push({
          id,
          mime,
          previewUrl,
          downloadUrl: asString(entry.download_url) ?? asString(entry.downloadUrl),
          sha256: asString(entry.sha256),
          fileName: asString(entry.filename) ?? asString(entry.name),
        });
      }
    }
  }

  return out;
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}
