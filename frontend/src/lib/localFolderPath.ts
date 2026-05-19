/** Strip bidi / directionality marks often copied from terminals or PDFs. */
const BIDI_AND_INVISIBLE = /[\u200E\u200F\u202A-\u202E\u2066-\u2069]/g;

function lineLooksLikeFilesystemPath(line: string): boolean {
  const t = line.replace(BIDI_AND_INVISIBLE, '').trim();
  if (!t) return false;
  if (/^file:/i.test(t)) return true;
  if (/^["']?file:/i.test(t)) return true;
  if (/^["']?\//.test(t)) return true;
  if (/^["']?~/.test(t)) return true;
  if (/^["']?[A-Za-z]:[\\/]/.test(t)) return true;
  if (/^["']?\/[A-Za-z]:[\\/]/.test(t)) return true;
  return false;
}

function pickPrimaryPathLine(raw: string): string {
  const lines = raw
    .split(/\r?\n/)
    .map((line) => line.replace(BIDI_AND_INVISIBLE, '').trim());
  const nonEmpty = lines.filter(Boolean);
  const pathish = nonEmpty.find(lineLooksLikeFilesystemPath);
  if (pathish) return pathish;
  return nonEmpty[0] ?? raw.replace(BIDI_AND_INVISIBLE, '').trim();
}

/**
 * Normalize a user-pasted or dropped folder path before sending to
 * ``POST …/authorized-paths`` (server still validates with ``expanduser`` + resolve).
 *
 * Handles: outer quotes, ``file://`` URLs (incl. percent-encoding), choosing the best
 * line when the clipboard contains multiple lines, and common invisible characters.
 */
export function normalizeLocalFolderPathForGrant(input: string): string {
  let s = String(input ?? '').replace(BIDI_AND_INVISIBLE, '').trim();
  if (!s) return '';

  s = pickPrimaryPathLine(s);

  if (
    (s.startsWith('"') && s.endsWith('"') && s.length >= 2) ||
    (s.startsWith("'") && s.endsWith("'") && s.length >= 2)
  ) {
    s = s.slice(1, -1).replace(BIDI_AND_INVISIBLE, '').trim();
  }

  if (/^file:/i.test(s)) {
    try {
      const u = new URL(s);
      if (u.protocol === 'file:') {
        let p = u.pathname;
        try {
          p = decodeURIComponent(p);
        } catch {
          // keep encoded pathname
        }
        s = p;
      }
    } catch {
      s = s.replace(/^file:\/\//i, '');
      try {
        s = decodeURIComponent(s);
      } catch {
        // keep
      }
    }
  }

  return s.replace(BIDI_AND_INVISIBLE, '').trim();
}
