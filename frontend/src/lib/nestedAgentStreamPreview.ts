import { pickCodeExecutionSourcePreview } from '@/lib/codeExecutionStreamPreview';
import { extToLanguage } from '@/pages/FolderPage/project/extToLanguage';

/**
 * Extract a string value for `key` from a growing JSON tool-arguments fragment.
 * Mirrors {@link pickCodeExecutionSourcePreview} (string-literal tail scan).
 */
function pickJsonStringField(
  key: string,
  raw: string,
  partialArgs?: Record<string, unknown>,
): string {
  const ps = partialArgs?.[key];
  if (typeof ps === 'string' && ps.length > 0) {
    return ps;
  }
  try {
    const j = JSON.parse(raw) as Record<string, unknown>;
    const u = j[key];
    if (typeof u === 'string') return u;
  } catch {
    /* incomplete JSON while streaming */
  }
  const needle = `"${key}"`;
  const keyIdx = raw.indexOf(needle);
  if (keyIdx === -1) {
    return raw.length > 12000 ? `${raw.slice(0, 12000)}\n…` : raw;
  }
  const slice = raw.slice(keyIdx);
  const colon = slice.indexOf(':');
  if (colon === -1) return raw.slice(0, 8000);
  let rest = slice.slice(colon + 1).trimStart();
  if (!rest.startsWith('"')) {
    return raw.slice(0, 8000);
  }
  rest = rest.slice(1);
  let out = '';
  for (let i = 0; i < rest.length; i += 1) {
    const c = rest[i];
    if (c === '\\') {
      const n = rest[i + 1];
      if (n === 'n') out += '\n';
      else if (n === 't') out += '\t';
      else if (n === 'r') out += '\r';
      else if (n === '"' || n === '\\') out += n ?? '';
      else if (n !== undefined) out += n;
      i += 1;
      continue;
    }
    if (c === '"') break;
    out += c ?? '';
  }
  return out || raw.slice(0, 8000);
}

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
  return argumentsRaw.length > 12000 ? `${argumentsRaw.slice(0, 12000)}\n…` : argumentsRaw;
}

export function languageForNestedPreview(
  toolName: string,
  argumentsPartial?: Record<string, unknown>,
): string {
  if (toolName === 'code_execution') return 'python';
  if (toolName === 'project_apply_patch') return 'diff';
  const p = argumentsPartial?.path;
  if (typeof p === 'string' && p.length > 0) {
    return extToLanguage(p);
  }
  return 'text';
}
