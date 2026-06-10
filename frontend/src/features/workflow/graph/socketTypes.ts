/**
 * Typed-socket model for the workflow editor.
 *
 * Ported from the backend `leagent/workflow/io/types.py` so the editor can
 * type-check links client-side before they ever reach the server. The colour
 * legend mirrors `SOCKET_COLORS`; the backend also ships its own legend over
 * `/object_info` (`socket_colors`) which, when present, overrides these
 * defaults at runtime.
 *
 * Design borrows from `@comfyorg/litegraph`'s slot-typing approach (each slot
 * carries a wire type; links are only valid between compatible types) without
 * adopting litegraph's canvas runtime.
 */

export const WILDCARD_TYPE = '*';

/** Default `io_type -> colour` legend (kept in sync with the backend). */
export const DEFAULT_SOCKET_COLORS: Record<string, string> = {
  STRING: '#7BD88F',
  INT: '#6E9BF5',
  FLOAT: '#4FC1E9',
  BOOLEAN: '#E9A23B',
  COMBO: '#B98EFF',
  OBJECT: '#D98AA8',
  ARRAY: '#E0A458',
  FILE: '#5AC8A8',
  IMAGE: '#64B5F6',
  AUDIO: '#F06292',
  VIDEO: '#BA68C8',
  DATETIME: '#90A4AE',
  MULTI: '#9E9E9E',
  [WILDCARD_TYPE]: '#C0C0C0',
};

export const DEFAULT_SOCKET_COLOR = '#A0A0A0';

/**
 * Resolve the colour for a wire type, consulting a runtime legend first
 * (from `/object_info`), then the static defaults, then a multi-type member,
 * then the fallback.
 */
export function socketColor(
  ioType: string,
  legend: Record<string, string> = DEFAULT_SOCKET_COLORS,
): string {
  if (legend[ioType]) return legend[ioType];
  if (DEFAULT_SOCKET_COLORS[ioType]) return DEFAULT_SOCKET_COLORS[ioType];
  if (ioType.includes(',')) {
    for (const member of ioType.split(',')) {
      if (legend[member]) return legend[member];
      if (DEFAULT_SOCKET_COLORS[member]) return DEFAULT_SOCKET_COLORS[member];
    }
    return legend.MULTI ?? DEFAULT_SOCKET_COLORS.MULTI ?? DEFAULT_SOCKET_COLOR;
  }
  return DEFAULT_SOCKET_COLOR;
}

/**
 * Return true if a link from an `upstream` output type into a `downstream`
 * input type is allowed. Mirrors `types_compatible()`:
 *
 * 1. Wildcard `"*"` on either side always matches.
 * 2. Exact string equality matches.
 * 3. Multi-type descriptors (`"A,B"`) match if the sets intersect.
 */
export function typesCompatible(upstream: string, downstream: string): boolean {
  if (upstream === WILDCARD_TYPE || downstream === WILDCARD_TYPE) return true;
  if (upstream === downstream) return true;
  const up = upstream.includes(',') ? new Set(upstream.split(',')) : new Set([upstream]);
  const down = downstream.includes(',')
    ? new Set(downstream.split(','))
    : new Set([downstream]);
  for (const t of up) {
    if (down.has(t)) return true;
  }
  return false;
}
