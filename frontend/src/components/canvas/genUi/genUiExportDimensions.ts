/** Capture sizes aligned with PDF export: full bleed for documents, min 16:9 for slide decks. */

export const SLIDE_EXPORT_WIDTH = 1280;
export const SLIDE_EXPORT_HEIGHT = 720;

/** Full content box after scroll containers are expanded (see {@link expandScrollContainersForCapture}). */
export function documentScreenshotDimensions(el: HTMLElement): { width: number; height: number } {
  const w = Math.max(1, Math.ceil(el.scrollWidth));
  const h = Math.max(1, Math.ceil(el.scrollHeight));
  return { width: w, height: h };
}

/**
 * Slide deck capture: at least 1280×720; grows with tall/wide slide content so exports are not clipped.
 */
export function deckScreenshotDimensions(el: HTMLElement): { width: number; height: number } {
  const w = Math.max(SLIDE_EXPORT_WIDTH, Math.ceil(el.scrollWidth));
  const h = Math.max(SLIDE_EXPORT_HEIGHT, Math.ceil(el.scrollHeight));
  return { width: w, height: h };
}
