import { describe, expect, it } from 'vitest';
import {
  canvasIframeAllow,
  canvasIframeSandbox,
  resolveCanvasPreviewIframeSandbox,
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

  it('includes allow-scripts and allow-same-origin for API canvas preview', () => {
    const sb = canvasIframeSandbox(true, true);
    expect(sb).toContain('allow-scripts');
    expect(sb).toContain('allow-same-origin');
    expect(sb).toContain('allow-popups');
  });

  it('omits allow-same-origin for non-API hosted preview without camera', () => {
    const sb = canvasIframeSandbox(true, false);
    expect(sb).toContain('allow-scripts');
    expect(sb).not.toContain('allow-same-origin');
  });
});

describe('srcDocIframeSandbox', () => {
  it('returns popups + scripts when enabled', () => {
    expect(srcDocIframeSandbox(false)).toBe('');
    expect(srcDocIframeSandbox(true)).toBe(
      'allow-scripts allow-popups allow-popups-to-escape-sandbox',
    );
  });
});

describe('resolveCanvasPreviewIframeSandbox', () => {
  it('omits sandbox in embedded srcDoc mode', () => {
    expect(
      resolveCanvasPreviewIframeSandbox({
        jsEnabled: true,
        mode: 'srcDoc',
        isApiCanvasPreview: true,
        cameraAllowed: false,
        embeddedHost: true,
      }),
    ).toBeUndefined();
  });
});
