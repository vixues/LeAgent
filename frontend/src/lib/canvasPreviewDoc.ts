/** Detect hosts (Cursor Simple Browser, VS Code webview) that block nested sandboxed ``src`` iframes. */
export function isEmbeddedAppBrowser(): boolean {
  if (typeof window === 'undefined') return false;
  const ua = navigator.userAgent;
  if (/Cursor/i.test(ua) || /vscode-webview/i.test(ua)) return true;
  try {
    if (window.self !== window.top) {
      const host = window.location.hostname;
      if (host === 'localhost' || host === '127.0.0.1') return true;
    }
  } catch {
    return true;
  }
  return false;
}

/** Ensure root-relative ``/api/v1/...`` asset URLs resolve when HTML is rendered via ``srcDoc``. */
export function injectCanvasPreviewBase(html: string, origin: string): string {
  const trimmed = html.trim();
  if (!trimmed) return html;
  if (/<base\b/i.test(trimmed)) return html;

  const baseHref = `${origin.replace(/\/$/, '')}/`;
  const tag = `<base href="${baseHref}">`;

  const headClose = trimmed.match(/<\/head\s*>/i);
  if (headClose?.index != null) {
    return `${trimmed.slice(0, headClose.index)}${tag}\n${trimmed.slice(headClose.index)}`;
  }

  const headOpen = trimmed.match(/<head[^>]*>/i);
  if (headOpen?.index != null && headOpen[0]) {
    const insertAt = headOpen.index + headOpen[0].length;
    return `${trimmed.slice(0, insertAt)}\n${tag}\n${trimmed.slice(insertAt)}`;
  }

  const htmlOpen = trimmed.match(/<html[^>]*>/i);
  if (htmlOpen?.index != null && htmlOpen[0]) {
    const insertAt = htmlOpen.index + htmlOpen[0].length;
    return `${trimmed.slice(0, insertAt)}\n<head>${tag}</head>\n${trimmed.slice(insertAt)}`;
  }

  return `${tag}\n${trimmed}`;
}
