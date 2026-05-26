import type { Message } from '@/types/chat';

export interface SessionEditPath {
  /** Relative or absolute project path touched by a tool. */
  path: string;
  tool: string;
  messageId: string;
}

function pushPath(
  out: SessionEditPath[],
  dedupe: Set<string>,
  path: string,
  tool: string,
  messageId: string,
) {
  const p = path.trim();
  if (!p) return;
  if (dedupe.has(p)) return;
  dedupe.add(p);
  out.push({ path: p, tool, messageId });
}

/** Extract ``+++ b/path`` / ``--- a/path`` targets from a unified diff. */
function pathsFromUnifiedDiff(diff: string): string[] {
  const paths: string[] = [];
  for (const line of diff.split('\n')) {
    if (line.startsWith('+++ ') || line.startsWith('--- ')) {
      const raw = line.slice(4).trim();
      if (raw === '/dev/null') continue;
      const normalized = raw.replace(/^[ab]\//, '').trim();
      if (normalized) paths.push(normalized);
    }
  }
  return paths;
}

/**
 * Collect project paths touched by ``project_*`` / ``coding_agent`` tool
 * calls in the session transcript (for workspace “session edits” UI).
 */
export function collectSessionEditPaths(messages: Message[]): SessionEditPath[] {
  const out: SessionEditPath[] = [];
  const dedupe = new Set<string>();

  for (const m of messages) {
    if (m.role !== 'assistant' || !Array.isArray(m.toolCalls)) continue;
    for (const tc of m.toolCalls) {
      const name = tc.name;
      const args = tc.arguments ?? {};
      const mid = m.id;

      if (name === 'project_edit' || name === 'project_write') {
        const p = typeof args.path === 'string' ? args.path : '';
        pushPath(out, dedupe, p, name, mid);
      } else if (name === 'text_processor' || name === 'markdown_processor') {
        const p = typeof args.file_path === 'string' ? args.file_path : '';
        pushPath(out, dedupe, p, name, mid);
      } else if (name === 'project_apply_patch') {
        const diff = typeof args.diff === 'string' ? args.diff : '';
        for (const p of pathsFromUnifiedDiff(diff)) {
          pushPath(out, dedupe, p, name, mid);
        }
        const res = tc.result;
        if (res && typeof res === 'object' && !Array.isArray(res)) {
          const files = (res as Record<string, unknown>).files;
          if (Array.isArray(files)) {
            for (const f of files) {
              if (typeof f === 'string') pushPath(out, dedupe, f, name, mid);
            }
          }
        }
      } else if (name === 'coding_agent') {
        const res = tc.result;
        if (!res || typeof res !== 'object' || Array.isArray(res)) continue;
        const r = res as Record<string, unknown>;
        const files = r.changed_files;
        if (Array.isArray(files)) {
          for (const f of files) {
            if (typeof f === 'string') pushPath(out, dedupe, f, name, mid);
          }
        }
        const activity = r.activity;
        if (Array.isArray(activity)) {
          for (const row of activity) {
            if (!row || typeof row !== 'object') continue;
            const path = (row as Record<string, unknown>).path;
            const tool = (row as Record<string, unknown>).tool;
            if (typeof path === 'string' && typeof tool === 'string') {
              pushPath(out, dedupe, path, tool, mid);
            }
          }
        }
      }
    }
  }

  return out;
}
