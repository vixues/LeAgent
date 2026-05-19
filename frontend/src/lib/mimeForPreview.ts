/**
 * MIME resolution and classification for file previews in the client.
 * Keeps Office OOXML types out of “text” paths (e.g. DOCX is ZIP, not text/xml).
 */

const OFFICE_OOXML = /^application\/vnd\.openxmlformats\./i;
const OFFICE_MS = /^application\/vnd\.ms-/i;

const EXT_TO_MIME: Record<string, string> = {
  // Images
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  gif: 'image/gif',
  webp: 'image/webp',
  avif: 'image/avif',
  svg: 'image/svg+xml',
  bmp: 'image/bmp',
  ico: 'image/x-icon',
  heic: 'image/heic',
  // Text / data
  txt: 'text/plain',
  log: 'text/plain',
  env: 'text/plain',
  md: 'text/markdown',
  mdx: 'text/markdown',
  json: 'application/json',
  jsonl: 'application/jsonl',
  xml: 'application/xml',
  yml: 'text/yaml',
  yaml: 'text/yaml',
  csv: 'text/csv',
  css: 'text/css',
  html: 'text/html',
  htm: 'text/html',
  cjs: 'text/javascript',
  mjs: 'text/javascript',
  js: 'text/javascript',
  ts: 'text/typescript',
  mts: 'text/typescript',
  cts: 'text/typescript',
  tsx: 'text/typescript',
  jsx: 'text/javascript',
  // Documents
  pdf: 'application/pdf',
  doc: 'application/msword',
  docx:
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xls: 'application/vnd.ms-excel',
  xlsx:
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  ppt: 'application/vnd.ms-powerpoint',
  pptx:
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  odt: 'application/vnd.oasis.opendocument.text',
  ods: 'application/vnd.oasis.opendocument.spreadsheet',
  odp: 'application/vnd.oasis.opendocument.presentation',
};

/**
 * Best-effort MIME from filename when the API sends octet-stream, coarse `file_type`, or nothing.
 */
export function inferMimeFromFileName(fileName: string): string | null {
  const last = fileName.trim().split(/[/\\]/).pop() ?? '';
  const dot = last.lastIndexOf('.');
  if (dot < 0 || dot === last.length - 1) return null;
  const ext = last.slice(dot + 1).toLowerCase();
  return EXT_TO_MIME[ext] ?? null;
}

const OFFICE_EXT = new Set([
  'doc',
  'docx',
  'xls',
  'xlsx',
  'ppt',
  'pptx',
  'odt',
  'ods',
  'odp',
]);

function fileExtensionLower(fileName: string): string {
  const last = fileName.trim().split(/[/\\]/).pop() ?? '';
  const dot = last.lastIndexOf('.');
  if (dot < 0 || dot === last.length - 1) return '';
  return last.slice(dot + 1).toLowerCase();
}

/** Filename is a known Office / OpenDocument extension (used to block text preview). */
export function hasOfficePreviewExtension(fileName: string): boolean {
  const ext = fileExtensionLower(fileName);
  return OFFICE_EXT.has(ext);
}

/** MIME values often wrongly assigned to Word/Excel files on upload. */
function isAmbiguousOfficeHostMime(mime: string): boolean {
  const m = mime.toLowerCase();
  return (
    m === 'text/plain' ||
    m === 'application/zip' ||
    m === 'application/x-zip-compressed' ||
    m === 'binary/octet-stream' ||
    m === 'application/download'
  );
}

/**
 * Resolves a stable MIME for preview routing. Falls back to extension when missing,
 * `application/octet-stream`, or non-standard API values (e.g. "document" with no "/").
 * When the server sends `text/plain` or `application/zip` for a `.docx`, trust the extension.
 */
export function resolveEffectiveMime(
  raw: string | null | undefined,
  fileName: string,
): string {
  const normalized = (raw ?? '').trim().toLowerCase();
  const fromExt = inferMimeFromFileName(fileName);

  if (!normalized) {
    return fromExt ?? 'application/octet-stream';
  }
  if (!normalized.includes('/')) {
    return fromExt ?? 'application/octet-stream';
  }
  if (normalized === 'application/octet-stream') {
    return fromExt ?? 'application/octet-stream';
  }
  if (
    fromExt &&
    isOfficeDocumentMime(fromExt) &&
    isAmbiguousOfficeHostMime(normalized)
  ) {
    return fromExt;
  }
  return normalized;
}

export function isTextLikeMime(mime: string): boolean {
  const m = mime.toLowerCase();
  if (!m) return false;
  if (OFFICE_OOXML.test(m) || OFFICE_MS.test(m)) return false;
  if (m.startsWith('text/')) return true;
  if (
    m === 'application/json' ||
    m === 'application/jsonl' ||
    m === 'application/x-ndjson' ||
    m === 'text/x-ndjson' ||
    m.endsWith('+json')
  ) {
    return true;
  }
  if (
    m === 'text/xml' ||
    m === 'application/xml' ||
    m === 'application/atom+xml' ||
    m.endsWith('+xml')
  ) {
    return true;
  }
  if (m === 'text/yaml' || m === 'application/x-yaml' || m === 'text/x-yaml') {
    return true;
  }
  if (
    m === 'text/csv' ||
    m === 'application/csv' ||
    m === 'text/csv; charset=utf-8'
  ) {
    return true;
  }
  if (
    m === 'application/javascript' ||
    m === 'text/javascript' ||
    m === 'application/x-javascript' ||
    m === 'text/ecmascript'
  ) {
    return true;
  }
  if (
    m === 'text/typescript' ||
    m === 'application/typescript' ||
    m === 'text/tsx' ||
    m === 'text/jsx'
  ) {
    return true;
  }
  return false;
}

export function isJsonPreviewMime(mime: string): boolean {
  const m = mime.toLowerCase();
  return m === 'application/json' || m.endsWith('+json') || m === 'application/jsonl';
}

export function isMarkdownPreviewMime(mime: string): boolean {
  const m = mime.toLowerCase();
  return (
    m === 'text/markdown' ||
    m === 'text/x-markdown' ||
    m === 'text/md' ||
    m === 'text/mdx'
  );
}

/** CSV table preview: MIME or `.csv` extension (covers `text/plain` mislabels). */
export function isCsvPreviewMime(mime: string, fileName: string): boolean {
  const m = mime.toLowerCase();
  if (m === 'text/csv' || m === 'application/csv') return true;
  const last = fileName.trim().split(/[/\\]/).pop() ?? '';
  const dot = last.lastIndexOf('.');
  if (dot < 0 || dot === last.length - 1) return false;
  return last.slice(dot + 1).toLowerCase() === 'csv';
}

/** Word / Excel / PowerPoint / OpenDocument — no safe inline browser preview. */
export function isOfficeDocumentMime(mime: string): boolean {
  const m = mime.toLowerCase();
  if (OFFICE_OOXML.test(m) || OFFICE_MS.test(m)) return true;
  if (m === 'application/msword' || m === 'application/vnd.ms-excel') {
    return true;
  }
  if (m.startsWith('application/vnd.oasis.opendocument.')) return true;
  return false;
}

/** OOXML in-browser preview vs legacy binary Office vs OpenDocument. */
export type OfficePreviewRoute =
  | 'docx'
  | 'xlsx'
  | 'pptx'
  | 'legacy'
  | 'openDocument';

/**
 * Routes Office-class files for preview UI. Prefer filename extension, then MIME.
 * Returns null when the file does not look like an Office/OpenDocument type.
 */
export function getOfficePreviewRoute(
  fileName: string,
  effectiveMime: string,
): OfficePreviewRoute | null {
  const ext = fileExtensionLower(fileName);
  const m = effectiveMime.trim().toLowerCase();

  if (ext === 'docx' || ext === 'docm') return 'docx';
  if (ext === 'xlsx' || ext === 'xlsm') return 'xlsx';
  if (ext === 'pptx' || ext === 'pptm') return 'pptx';
  if (ext === 'doc' || ext === 'dot') return 'legacy';
  if (ext === 'xls' || ext === 'xlt') return 'legacy';
  if (ext === 'ppt' || ext === 'pps') return 'legacy';
  if (ext === 'odt' || ext === 'ods' || ext === 'odp') return 'openDocument';

  if (
    m.includes('wordprocessingml.document') ||
    m.includes('wordprocessingml.template')
  ) {
    return 'docx';
  }
  if (
    m.includes('spreadsheetml.sheet') ||
    m.includes('spreadsheetml.template')
  ) {
    return 'xlsx';
  }
  if (
    m.includes('presentationml.presentation') ||
    m.includes('presentationml.slideshow') ||
    m.includes('presentationml.template')
  ) {
    return 'pptx';
  }
  if (m === 'application/msword') return 'legacy';
  if (m === 'application/vnd.ms-excel') return 'legacy';
  if (m === 'application/vnd.ms-powerpoint') return 'legacy';
  if (m.startsWith('application/vnd.oasis.opendocument.')) {
    return 'openDocument';
  }

  if (OFFICE_OOXML.test(m) || OFFICE_MS.test(m)) {
    if (m.includes('wordprocessing') || m.includes('word')) return 'docx';
    if (m.includes('spreadsheet') || m.includes('excel')) return 'xlsx';
    if (m.includes('presentation') || m.includes('powerpoint')) return 'pptx';
    return 'legacy';
  }

  return null;
}

/**
 * Heuristic: decoded “text” is likely binary (ZIP/office or NULs).
 */
export function looksLikeBinaryString(value: string): boolean {
  if (value.length === 0) return false;
  const head = value.slice(0, 16384);
  if (head.includes('\0')) return true;
  if (head.startsWith('PK\x03\x04') || head.startsWith('PK\x05\x06')) {
    return true;
  }
  return false;
}
