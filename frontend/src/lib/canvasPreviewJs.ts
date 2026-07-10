/** Append or remove canvas preview query flags (``js``, ``camera``). */
export function withCanvasPreviewFlags(
  url: string,
  flags: { jsEnabled?: boolean; cameraAllowed?: boolean } = {},
): string {
  if (!url) return '';
  const { jsEnabled = false, cameraAllowed = false } = flags;
  try {
    const base =
      url.startsWith('http://') || url.startsWith('https://')
        ? undefined
        : typeof window !== 'undefined'
          ? window.location.origin
          : 'http://local.invalid';
    const u = new URL(url, base);
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
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return u.href;
    }
    return `${u.pathname}${u.search}${u.hash}`;
  } catch {
    return url;
  }
}

/** Append or remove the canvas preview ``js=1`` query flag. */
export function withCanvasPreviewJs(url: string, jsEnabled: boolean): string {
  return withCanvasPreviewFlags(url, { jsEnabled });
}

/** Permissions Policy delegation for camera/mic inside hosted canvas iframes. */
export function canvasIframeAllow(cameraAllowed: boolean): string | undefined {
  return cameraAllowed ? 'camera *; microphone *' : undefined;
}

/**
 * Sandbox token for hosted canvas iframes loaded via ``src`` (same-origin preview URL).
 * ``allow-same-origin`` is required when JS is on so WebGL / ``/api/v1/files`` assets
 * inside the preview resolve against the app origin (opaque sandbox origins break Three.js).
 */
export function canvasIframeSandbox(
  jsEnabled: boolean,
  isApiCanvasPreview: boolean,
  cameraAllowed = false,
): string {
  if (!jsEnabled) {
    return isApiCanvasPreview
      ? 'allow-popups allow-popups-to-escape-sandbox'
      : '';
  }
  const tokens = isApiCanvasPreview
    ? ['allow-scripts', 'allow-same-origin', 'allow-popups', 'allow-popups-to-escape-sandbox']
    : ['allow-scripts'];
  if (cameraAllowed && !tokens.includes('allow-same-origin')) {
    tokens.push('allow-same-origin');
  }
  return tokens.join(' ');
}

/** Sandbox token for local ``srcDoc`` previews (SandboxedPreview, HtmlFrame, API canvas fetch). */
export function srcDocIframeSandbox(jsEnabled: boolean): string {
  if (!jsEnabled) return '';
  return 'allow-scripts allow-popups allow-popups-to-escape-sandbox';
}

export type CanvasPreviewSandboxMode = 'srcDoc' | 'src';

/** Pick iframe sandbox tokens for canvas preview; omit attribute when ``undefined``. */
export function resolveCanvasPreviewIframeSandbox(options: {
  jsEnabled: boolean;
  mode: CanvasPreviewSandboxMode;
  isApiCanvasPreview: boolean;
  cameraAllowed: boolean;
  embeddedHost: boolean;
}): string | undefined {
  const { jsEnabled, mode, isApiCanvasPreview, cameraAllowed, embeddedHost } = options;

  if (embeddedHost && jsEnabled && isApiCanvasPreview && mode === 'srcDoc') {
    return undefined;
  }

  if (mode === 'srcDoc') {
    const sb = srcDocIframeSandbox(jsEnabled);
    return sb || undefined;
  }

  const sb = canvasIframeSandbox(jsEnabled, isApiCanvasPreview, cameraAllowed);
  return sb || undefined;
}
