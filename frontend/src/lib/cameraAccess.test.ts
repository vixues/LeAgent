import { afterEach, describe, expect, it, vi } from 'vitest';
import { getCameraAccessIssue, localhostPreviewUrl, stopIframeMediaTracks } from './cameraAccess';

describe('getCameraAccessIssue', () => {
  const origSecure = Object.getOwnPropertyDescriptor(window, 'isSecureContext');

  afterEach(() => {
    if (origSecure) {
      Object.defineProperty(window, 'isSecureContext', origSecure);
    }
    vi.unstubAllGlobals();
  });

  it('returns insecure when not a secure context', () => {
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: false });
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: vi.fn() } });
    expect(getCameraAccessIssue()).toBe('insecure');
  });

  it('returns null on secure context with getUserMedia', () => {
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: true });
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: vi.fn() } });
    expect(getCameraAccessIssue()).toBeNull();
  });
});

describe('stopIframeMediaTracks', () => {
  it('calls __leagentReleaseMedia when present', () => {
    const release = vi.fn();
    const iframe = {
      contentWindow: { __leagentReleaseMedia: release, document: { querySelectorAll: () => [] } },
    } as unknown as HTMLIFrameElement;
    stopIframeMediaTracks(iframe);
    expect(release).toHaveBeenCalledOnce();
  });
});

describe('localhostPreviewUrl', () => {
  it('rewrites relative preview path to localhost with js flag', () => {
    vi.stubGlobal('location', { ...window.location, port: '5173' });
    expect(localhostPreviewUrl('/api/v1/canvas/preview?token=abc', true)).toBe(
      'http://localhost:5173/api/v1/canvas/preview?token=abc&js=1&camera=1',
    );
  });
});
