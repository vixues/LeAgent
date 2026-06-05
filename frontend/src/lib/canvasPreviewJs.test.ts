import { describe, expect, it } from 'vitest';
import {
  canvasIframeSandbox,
  srcDocIframeSandbox,
  withCanvasPreviewJs,
} from './canvasPreviewJs';

describe('withCanvasPreviewJs', () => {
  it('appends js=1 when enabled', () => {
    const out = withCanvasPreviewJs('/api/v1/canvas/preview?token=abc', true);
    expect(out).toContain('js=1');
  });

  it('removes js when disabled', () => {
    const out = withCanvasPreviewJs('/api/v1/canvas/preview?token=abc&js=1', false);
    expect(out).not.toContain('js=1');
  });
});

describe('canvasIframeSandbox', () => {
  it('omits allow-scripts when JS disabled', () => {
    expect(canvasIframeSandbox(false, true)).not.toContain('allow-scripts');
  });

  it('includes allow-scripts without allow-same-origin when JS enabled', () => {
    const sb = canvasIframeSandbox(true, true);
    expect(sb).toContain('allow-scripts');
    expect(sb).not.toContain('allow-same-origin');
  });
});

describe('srcDocIframeSandbox', () => {
  it('returns allow-scripts only when enabled', () => {
    expect(srcDocIframeSandbox(false)).toBe('');
    expect(srcDocIframeSandbox(true)).toBe('allow-scripts');
  });
});
