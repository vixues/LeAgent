/** Why camera / getUserMedia may be unavailable in the host page. */
export type CameraAccessIssue = 'insecure' | 'unsupported' | 'denied';

/** Detect blocking issues before calling ``getUserMedia``. */
export function getCameraAccessIssue(): CameraAccessIssue | null {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return 'unsupported';
  }
  if (!window.isSecureContext) {
    return 'insecure';
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    return 'unsupported';
  }
  return null;
}

/** Stop camera/mic tracks inside a same-origin preview iframe before reload. */
export function stopIframeMediaTracks(iframe: HTMLIFrameElement | null): void {
  if (!iframe) return;
  try {
    const win = iframe.contentWindow as (Window & { __leagentReleaseMedia?: () => void }) | null;
    win?.__leagentReleaseMedia?.();
    const doc = win?.document;
    if (!doc) return;
    doc.querySelectorAll('video, audio').forEach((el) => {
      const media = el as HTMLMediaElement;
      const stream = media.srcObject;
      if (stream instanceof MediaStream) {
        stream.getTracks().forEach((track) => track.stop());
      }
      media.srcObject = null;
    });
  } catch {
    // iframe may still be opaque (camera not yet authorized)
  }
}

/** Defer iframe remount so the OS releases the camera device. */
export function schedulePreviewIframeReload(reload: () => void, delayMs = 80): void {
  if (typeof window === 'undefined') {
    reload();
    return;
  }
  window.setTimeout(reload, delayMs);
}

/** Build a localhost preview URL for camera use when the SPA is opened via LAN IP. */
export function localhostPreviewUrl(
  previewPath: string,
  jsEnabled: boolean,
  cameraAllowed = true,
): string {
  const port =
    typeof window !== 'undefined' && window.location.port ? window.location.port : '5173';
  let path = previewPath;
  if (path.startsWith('http://') || path.startsWith('https://')) {
    try {
      const u = new URL(path);
      path = `${u.pathname}${u.search}${u.hash}`;
    } catch {
      path = previewPath;
    }
  }
  if (!path.startsWith('/')) {
    path = `/${path}`;
  }
  const u = new URL(path, `http://localhost:${port}`);
  if (jsEnabled) {
    u.searchParams.set('js', '1');
  } else {
    u.searchParams.delete('js');
  }
  if (cameraAllowed) {
    u.searchParams.set('camera', '1');
  } else {
    u.searchParams.delete('camera');
  }
  return u.href;
}
