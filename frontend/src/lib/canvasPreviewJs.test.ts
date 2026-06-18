import { describe, expect, it } from 'vitest';
import {
  canvasIframeAllow,
  canvasIframeSandbox,
  srcDocIframeSandbox,
  withCanvasPreviewFlags,
  withCanvasPreviewJs,
} from './canvasPreviewJs';

describe('withCanvasPreviewJs', () => {
  it('appends js=1 when enabled', () => {
    const out = withCanvasPreviewJs('/api/v1/canvas/preview?token=abc', true);
    expect(out).toContain('js=1');
  });

  it('appends camera=1 when camera allowed', () => {
    const out = withCanvasPreviewFlags('/api/v1/canvas/preview?token=abc', {
      jsEnabled: true,
      cameraAllowed: true,
    });
    expect(out).toContain('js=1');
    expect(out).toContain('camera=1');
  });

  it('removes js when disabled', () => {
    const out = withCanvasPreviewJs('/api/v1/canvas/preview?token=abc&js=1', false);
    expect(out).not.toContain('js=1');
  });
});

describe('canvasIframeAllow', () => {
  it('returns camera policy when allowed', () => {
    expect(canvasIframeAllow(true)).toBe('camera *; microphone *');
  });

  it('returns undefined when not allowed', () => {
    expect(canvasIframeAllow(false)).toBeUndefined();
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

  it('adds allow-same-origin when camera authorized', () => {
    const sb = canvasIframeSandbox(true, true, true);
    expect(sb).toContain('allow-scripts');
    expect(sb).toContain('allow-same-origin');
  });
});

describe('srcDocIframeSandbox', () => {
  it('returns allow-scripts only when enabled', () => {
    expect(srcDocIframeSandbox(false)).toBe('');
    expect(srcDocIframeSandbox(true)).toBe('allow-scripts');
  });
});
