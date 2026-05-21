import { describe, expect, it } from 'vitest';
import { extractCanvasPreviewToken } from './canvasScreenshot';

describe('extractCanvasPreviewToken', () => {
  it('reads token from relative canvas preview path', () => {
    expect(
      extractCanvasPreviewToken('/api/v1/canvas/preview?token=signed.jwt.token.here'),
    ).toBe('signed.jwt.token.here');
  });

  it('reads token from absolute preview URL', () => {
    expect(
      extractCanvasPreviewToken(
        'https://app.example/api/v1/canvas/preview?token=abc1234567890',
      ),
    ).toBe('abc1234567890');
  });

  it('returns null for non-canvas paths', () => {
    expect(
      extractCanvasPreviewToken('/api/v1/files/uuid/preview?token=signed'),
    ).toBeNull();
  });

  it('returns null when token missing or too short', () => {
    expect(extractCanvasPreviewToken('/api/v1/canvas/preview')).toBeNull();
    expect(extractCanvasPreviewToken('/api/v1/canvas/preview?token=short')).toBeNull();
  });
});
