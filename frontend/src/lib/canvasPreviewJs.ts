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
 * Sandbox token for hosted canvas iframes.
 * ``allow-same-origin`` is added only when the user explicitly authorizes camera —
 * required by browsers for ``getUserMedia`` inside a sandboxed iframe (opaque origin
 * otherwise always denies). Avoid combining ``allow-scripts`` + ``allow-same-origin``
 * unless camera is requested.
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
    ? ['allow-scripts', 'allow-popups', 'allow-popups-to-escape-sandbox', 'allow-same-origin']
    : ['allow-scripts'];
  if (cameraAllowed) {
    tokens.push('allow-same-origin');
  }
  return tokens.join(' ');
}

/** Sandbox token for local srcDoc previews (SandboxedPreview, HtmlFrame). */
export function srcDocIframeSandbox(jsEnabled: boolean): string {
  return jsEnabled ? 'allow-scripts' : '';
}
