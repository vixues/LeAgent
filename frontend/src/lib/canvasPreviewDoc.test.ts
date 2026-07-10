import { describe, expect, it } from 'vitest';
import { injectCanvasPreviewBase } from './canvasPreviewDoc';

describe('injectCanvasPreviewBase', () => {
  it('inserts base before </head>', () => {
    const html = '<!DOCTYPE html><html><head><title>x</title></head><body></body></html>';
    const out = injectCanvasPreviewBase(html, 'http://localhost:5173');
    expect(out).toContain('<base href="http://localhost:5173/">');
  });

  it('skips when base already present', () => {
    const html = '<html><head><base href="/"></head><body></body></html>';
    expect(injectCanvasPreviewBase(html, 'http://localhost:5173')).toBe(html);
  });
});
