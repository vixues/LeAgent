import { STREAM_PREVIEW_FALLBACK_CHARS } from '@/lib/streamPreviewLimits';

/**
 * Extract a string value for `key` from a growing JSON tool-arguments fragment.
 * Used while the model streams tool-call arguments (SSE tool_call_delta).
 */
export function pickJsonStringField(
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
    return raw.length > STREAM_PREVIEW_FALLBACK_CHARS
      ? `${raw.slice(0, STREAM_PREVIEW_FALLBACK_CHARS)}\n…`
      : raw;
  }
  const slice = raw.slice(keyIdx);
  const colon = slice.indexOf(':');
  if (colon === -1) return raw.slice(0, STREAM_PREVIEW_FALLBACK_CHARS);
  let rest = slice.slice(colon + 1).trimStart();
  if (!rest.startsWith('"')) {
    return raw.slice(0, STREAM_PREVIEW_FALLBACK_CHARS);
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
  return out || raw.slice(0, STREAM_PREVIEW_FALLBACK_CHARS);
}

/** Best-effort operation name from partial tool-call JSON. */
export function pickJsonStringOperation(
  raw: string,
  partialArgs?: Record<string, unknown>,
): string {
  const fromPartial = partialArgs?.operation;
  if (typeof fromPartial === 'string' && fromPartial.trim()) {
    return fromPartial.trim();
  }
  return pickJsonStringField('operation', raw, partialArgs).trim();
}
