/** Append or remove the canvas preview ``js=1`` query flag. */
export function withCanvasPreviewJs(url: string, jsEnabled: boolean): string {
  if (!url) return '';
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
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return u.href;
    }
    return `${u.pathname}${u.search}${u.hash}`;
  } catch {
    return url;
  }
}

/** Sandbox token for hosted canvas iframes — avoid allow-scripts + allow-same-origin. */
export function canvasIframeSandbox(jsEnabled: boolean, isApiCanvasPreview: boolean): string {
  if (!jsEnabled) {
    return isApiCanvasPreview
      ? 'allow-popups allow-popups-to-escape-sandbox'
      : '';
  }
  return isApiCanvasPreview
    ? 'allow-scripts allow-popups allow-popups-to-escape-sandbox'
    : 'allow-scripts';
}

/** Sandbox token for local srcDoc previews (SandboxedPreview, HtmlFrame). */
export function srcDocIframeSandbox(jsEnabled: boolean): string {
  return jsEnabled ? 'allow-scripts' : '';
}
