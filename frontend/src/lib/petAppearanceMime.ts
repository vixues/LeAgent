/**
 * Pet appearance / nest background: treat common raster + vector + GIF types as renderable,
 * including uploads where the browser sent `application/octet-stream` but the filename is correct.
 */
export function effectivePetImageMime(
  mime: string | null | undefined,
  hintFilename?: string | null,
): string | null {
  if (mime && mime.startsWith('image/')) return mime;
  if (!hintFilename) return null;
  const ext = hintFilename.split('.').pop()?.toLowerCase() ?? '';
  const byExt: Record<string, string> = {
    svg: 'image/svg+xml',
    gif: 'image/gif',
    png: 'image/png',
    webp: 'image/webp',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    bmp: 'image/bmp',
    avif: 'image/avif',
  };
  const guessed = byExt[ext];
  if (!guessed) return null;
  if (!mime || mime === 'application/octet-stream') return guessed;
  return null;
}

export function isPetRenderableImageRow(row: { mime_type: string | null; original_name: string }): boolean {
  return effectivePetImageMime(row.mime_type, row.original_name) !== null;
}
