/**
 * Best-effort HTML extraction from a growing canvas_publish JSON argument string.
 */
export function pickCanvasHtmlPreview(
  raw: string,
  partialArgs?: Record<string, unknown>,
): string {
  const ph = partialArgs?.html;
  if (typeof ph === 'string' && ph.length > 0) {
    return ph;
  }
  try {
    const j = JSON.parse(raw) as { html?: unknown };
    if (typeof j.html === 'string') return j.html;
  } catch {
    /* incomplete JSON while streaming */
  }
  const keyIdx = raw.indexOf('"html"');
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
