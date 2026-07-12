import { describe, expect, it } from 'vitest';
import { pickCanvasHtmlPreview } from './canvasStreamPreview';
import { STREAM_PREVIEW_FALLBACK_CHARS } from './streamPreviewLimits';

describe('pickCanvasHtmlPreview', () => {
  it('uses STREAM_PREVIEW_FALLBACK_CHARS when html key is missing', () => {
    const raw = 'x'.repeat(STREAM_PREVIEW_FALLBACK_CHARS + 50);
    const out = pickCanvasHtmlPreview(raw, {});
    expect(out.startsWith('x'.repeat(STREAM_PREVIEW_FALLBACK_CHARS))).toBe(true);
    expect(out.endsWith('\n…')).toBe(true);
    expect(out.length).toBe(STREAM_PREVIEW_FALLBACK_CHARS + 2);
  });

  it('extracts streaming html field', () => {
    const raw = '{"title":"t","html":"<div>hi","mode":"html"';
    expect(pickCanvasHtmlPreview(raw, {})).toBe('<div>hi');
  });
});
