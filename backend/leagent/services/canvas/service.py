"""Persist canvas revisions, mint preview tokens, and serve HTML."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlmodel import col, func, select

from leagent.services.auth.tokens import mint_token, decode_token, TokenError

from leagent.services.auth.signed_url import sign_managed_file_urls_in_html
from leagent.services.canvas.html_bundle import merge_html_files_to_document
from leagent.db.models.canvas import CanvasContentType, CanvasDocument
from leagent.db.models.message import ChatSession
from leagent.services.gen_ui.schema import validate_ui_tree, ui_tree_from_json_bytes

if TYPE_CHECKING:
    from leagent.config.settings import Settings
    from leagent.services.chat.service import ChatService
    from leagent.db.service import DatabaseService

logger = logging.getLogger(__name__)

ALLOWED_EMBED_NETLOCS: frozenset[str] = frozenset(
    {
        "www.google.com",
        "google.com",
        "maps.google.com",
        "www.openstreetmap.org",
        "openstreetmap.org",
        "www.youtube.com",
        "youtube.com",
        "player.vimeo.com",
    }
)

MAPS_KEY_PLACEHOLDER = "__LEAGENT_MAPS_KEY__"


def _signing_secret(settings: Settings) -> str:
    s = (settings.canvas.preview_signing_secret or "").strip()
    if s:
        return s
    return "leagent-local-secret"


def mint_preview_token(
    settings: Settings,
    *,
    canvas_id: UUID,
    revision: int,
    user_id: UUID,
) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=max(60, settings.canvas.preview_token_ttl_seconds))
    payload = {
        "cid": str(canvas_id),
        "rev": revision,
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "aud": "leagent-canvas-preview",
    }
    return mint_token(payload, _signing_secret(settings))


def decode_preview_token(settings: Settings, token: str) -> dict[str, Any]:
    return decode_token(
        token,
        _signing_secret(settings),
        audience="leagent-canvas-preview",
        options={"require_exp": True},
    )


def preview_query_path(token: str) -> str:
    from urllib.parse import quote

    return f"/api/v1/canvas/preview?token={quote(token, safe='')}"


# --- HTML sanitisation + preview shell ------------------------------------
#
# The agent ships HTML through two shapes:
#   * Body fragments (no <html>) — Tailwind CDN + base styles are wrapped
#     around them later. We pass these through nh3 with a relaxed allowlist
#     that keeps `class`/`style`/`id` attributes plus inline SVG so Tailwind
#     utilities and chart primitives survive.
#   * Full <!DOCTYPE html> documents — nh3 is a fragment cleaner that strips
#     <html>/<head>/<body>/<style>, which would obliterate the Tailwind shell
#     and any inline stylesheet. We instead run a narrow scrubber that only
#     strips genuinely dangerous bits (untrusted <script>, inline event
#     handlers, javascript: URLs) and lets the rest through. Hosting is in a
#     sandboxed iframe with a strict CSP, which provides defence in depth.
#
# Preview-asset injection for full documents is conditional: bare shells and
# Tailwind-utility pages get the host CDN shell; documents that already ship
# Tailwind or a substantial authored stylesheet pass through unchanged so
# Preflight / host body resets cannot clobber page-owned CSS.

_SCRIPT_SRC_ALLOWLIST: tuple[str, ...] = (
    "cdn.tailwindcss.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "cdn.jsdelivr.net",
    "unpkg.com",
)

# Hosted HTML preview needs a synchronous global so normal inline scripts can
# use ``window.THREE`` after the user enables JS. Three.js removed this global
# build in r161, so HTML preview pins the last global-compatible release while
# the React GenUI renderer uses the installed modern ``three`` package.
_THREE_JS_GLOBAL_CDN = "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"
_THREE_JS_BOOTSTRAP = f'<script src="{_THREE_JS_GLOBAL_CDN}"></script>\n'

# Match real Three.js loads only — not prose like "Three.js 未加载" in UI copy.
_THREE_SCRIPT_HINT_RE = re.compile(
    r"""(?ix)
    (?:
        <script\b[^>]*\bsrc\s*=\s*['\"][^'\"]*three(?:\.min)?\.js
      | /npm/three@
      | from\s+['\"]three['\"]
    )
    """
)


def _html_already_loads_three(html: str) -> bool:
    return bool(_THREE_SCRIPT_HINT_RE.search(html))


def _three_bootstrap_for_html(html: str) -> str:
    return "" if _html_already_loads_three(html) else _THREE_JS_BOOTSTRAP

_SVG_TAGS: frozenset[str] = frozenset(
    {
        "svg",
        "path",
        "g",
        "circle",
        "rect",
        "line",
        "polyline",
        "polygon",
        "ellipse",
        "defs",
        "linearGradient",
        "radialGradient",
        "stop",
        "text",
        "tspan",
        "use",
        "marker",
        "symbol",
        "title",
        "desc",
    }
)

_SVG_ATTRS: frozenset[str] = frozenset(
    {
        "viewBox",
        "d",
        "fill",
        "fill-opacity",
        "fill-rule",
        "stroke",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-dasharray",
        "stroke-opacity",
        "cx",
        "cy",
        "r",
        "rx",
        "ry",
        "x",
        "y",
        "x1",
        "y1",
        "x2",
        "y2",
        "width",
        "height",
        "points",
        "transform",
        "xmlns",
        "preserveAspectRatio",
        "offset",
        "stop-color",
        "stop-opacity",
        "gradientUnits",
        "gradientTransform",
        "patternUnits",
        "text-anchor",
        "dominant-baseline",
        "font-size",
        "font-family",
        "font-weight",
        "opacity",
    }
)

_SCRIPT_BLOCK_RE = re.compile(r"(?is)<script\b([^>]*)>(.*?)</script\s*>")
_SCRIPT_SELF_CLOSING_RE = re.compile(r"(?is)<script\b([^>]*)/>")
_INLINE_HANDLER_RE = re.compile(
    r"\s+on[a-z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
    flags=re.IGNORECASE,
)
_JS_URL_RE = re.compile(
    r"""(?ix)
    \s+(href|src|xlink:href|formaction|action|background)\s*=\s*
    (?:\"\s*javascript:[^\"]*\"|'\s*javascript:[^']*'|javascript:[^\s>]*)
    """,
)
_SCRIPT_SRC_RE = re.compile(
    r"""(?ix)\bsrc\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))""",
)


def _has_full_doc(raw: str) -> bool:
    return "<html" in raw.lower()


def _script_src_is_allowed(attrs: str) -> bool:
    """Return True when a <script> tag's src points at an allowlisted CDN."""
    m = _SCRIPT_SRC_RE.search(attrs)
    if not m:
        return False
    src = (m.group(1) or m.group(2) or m.group(3) or "").strip().lower()
    if not src:
        return False
    for host in _SCRIPT_SRC_ALLOWLIST:
        if host in src:
            return True
    return False


def _scrub_full_document(raw: str) -> str:
    """Narrow scrubber for full <!DOCTYPE html> documents.

    Removes <script> blocks (unless src= matches an allowlisted CDN),
    inline event handlers (on*=), and ``javascript:`` URLs. Everything else —
    <head>, <body>, <style>, <link>, class/style attributes, SVG — passes
    through. Defence in depth comes from the sandboxed iframe + CSP.
    """

    def _filter_script_block(match: re.Match[str]) -> str:
        attrs = match.group(1) or ""
        body = match.group(2) or ""
        if _script_src_is_allowed(attrs) and not body.strip():
            return match.group(0)
        return ""

    def _filter_self_closing_script(match: re.Match[str]) -> str:
        attrs = match.group(1) or ""
        if _script_src_is_allowed(attrs):
            return match.group(0)
        return ""

    cleaned = _SCRIPT_BLOCK_RE.sub(_filter_script_block, raw)
    cleaned = _SCRIPT_SELF_CLOSING_RE.sub(_filter_self_closing_script, cleaned)
    cleaned = _INLINE_HANDLER_RE.sub("", cleaned)
    cleaned = _JS_URL_RE.sub("", cleaned)
    return cleaned


def _build_nh3_cleaner() -> Any:
    """Create an nh3.Cleaner that preserves class/style/id and SVG primitives."""
    import nh3
    from copy import deepcopy

    tags = set(nh3.ALLOWED_TAGS) | {"style"} | _SVG_TAGS
    # nh3/ammonia forbid the same tag in both `tags` and `clean_content_tags`.
    # `style` is in CLEAN_CONTENT_TAGS by default (strip dangerous content);
    # we explicitly allow `<style>` in `tags`, so drop it from clean_content_tags.
    clean_content_tags = set(nh3.CLEAN_CONTENT_TAGS) - {"style"}
    attributes = deepcopy(nh3.ALLOWED_ATTRIBUTES)
    extra_global = {"class", "style", "id", "title", "role", "aria-label", "aria-hidden"}
    attributes.setdefault("*", set()).update(extra_global)
    for tag in _SVG_TAGS:
        attributes.setdefault(tag, set()).update(_SVG_ATTRS)
    return nh3.Cleaner(
        tags=tags,
        clean_content_tags=clean_content_tags,
        attributes=attributes,
        link_rel="noopener noreferrer",
        strip_comments=True,
    )


def _scrub_fragment_fallback(raw: str) -> str:
    """Best-effort fragment scrubber when nh3 is unavailable."""
    cleaned = _SCRIPT_BLOCK_RE.sub("", raw)
    cleaned = _SCRIPT_SELF_CLOSING_RE.sub("", cleaned)
    cleaned = _INLINE_HANDLER_RE.sub("", cleaned)
    cleaned = _JS_URL_RE.sub("", cleaned)
    return cleaned


def sanitize_html(html: str, *, max_bytes: int, allow_js: bool = False) -> str:
    """Sanitise agent-supplied HTML for safe hosted preview.

    Two paths:
      * Full <!DOCTYPE html> docs — narrow scrubber that keeps <head>,
        <body>, <style>, class/style attrs, SVG.
      * Body fragments — nh3.Cleaner with a relaxed allowlist that keeps
        Tailwind utility classes and inline styles.

    When ``allow_js`` is True, scripts and inline event handlers are kept
    (preview-time opt-in only; publish stores the raw HTML).
    """
    raw = html or ""
    if len(raw.encode("utf-8")) > max_bytes:
        raise ValueError(f"HTML exceeds max size ({max_bytes} bytes)")
    if allow_js:
        return raw
    if _has_full_doc(raw):
        return _scrub_full_document(raw)
    try:
        return _build_nh3_cleaner().clean(raw)
    except Exception:  # noqa: BLE001 — fall back to regex scrubber
        return _scrub_fragment_fallback(raw)


def _inject_maps_key(html: str, api_key: str) -> str:
    if not api_key or MAPS_KEY_PLACEHOLDER not in html:
        return html
    return html.replace(MAPS_KEY_PLACEHOLDER, api_key)


def _loopback_hostname(host: str) -> bool:
    h = (host or "").lower().strip("[]")
    return h in ("localhost", "127.0.0.1", "::1", "0:0:0:0:0:0:0:1")


def _validate_embed_url(url: str, *, allow_loopback: bool = False) -> str:
    from urllib.parse import urlparse

    u = urlparse(url.strip())
    if u.scheme not in ("https", "http"):
        raise ValueError("embed_url must be http(s)")
    host = (u.hostname or "").lower()
    if allow_loopback and _loopback_hostname(host):
        return url.strip()
    if host not in ALLOWED_EMBED_NETLOCS and not host.endswith(".google.com"):
        raise ValueError(f"embed hostname not allowed: {host}")
    return url.strip()


# Shared Tailwind + base CSS for canvas preview (fragment wrap and full-document inject).
_PREVIEW_HEAD_CORE = """
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet"/>
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  theme: {
    extend: {
      fontFamily: { sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'] },
      colors: {
        primary: {50:'#f0f9ff',100:'#e0f2fe',200:'#bae6fd',300:'#7dd3fc',400:'#38bdf8',500:'#0ea5e9',600:'#0284c7',700:'#0369a1',800:'#075985',900:'#0c4a6e'},
        surface: { DEFAULT:'#ffffff', elevated:'#ffffff', sunken:'#f1f5f9' },
      },
    },
  },
  darkMode: 'class',
}
</script>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; height: 100%; color-scheme: light; }
  body {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    color: #1a1a2e;
    background: #ffffff;
    line-height: 1.6;
    min-height: 100%;
  }
  body::-webkit-scrollbar { width: 0; height: 0; }
  body { scrollbar-width: none; }
  img { max-width: 100%; height: auto; }
  a { color: #0284c7; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .wa-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
  .wa-gradient { background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%); color: #fff; }
  .wa-gradient-warm { background: linear-gradient(135deg, #f97316 0%, #ec4899 100%); color: #fff; }
  .wa-gradient-fresh { background: linear-gradient(135deg, #10b981 0%, #0ea5e9 100%); color: #fff; }
  canvas { display: block; max-width: 100%; }
</style>
"""

_PREVIEW_IFRAME_BOOTSTRAP = """
<script>
(function () {
  function syncViewport() {
    var h = window.innerHeight || document.documentElement.clientHeight || 0;
    if (h > 0) {
      document.documentElement.style.height = h + 'px';
      document.body.style.minHeight = h + 'px';
    }
    window.dispatchEvent(new Event('resize'));
  }
  syncViewport();
  window.addEventListener('load', function () {
    syncViewport();
    setTimeout(syncViewport, 0);
    setTimeout(syncViewport, 120);
    setTimeout(syncViewport, 400);
  });
  window.addEventListener('resize', syncViewport);
  if (window.ResizeObserver) {
    try {
      new ResizeObserver(syncViewport).observe(document.documentElement);
    } catch (e) {}
  }
})();
</script>
"""


def _preview_head_assets(html: str) -> str:
    """Tailwind shell + optional Three.js global (skip when agent HTML already loads it)."""
    return _PREVIEW_HEAD_CORE + _three_bootstrap_for_html(html)


_PREVIEW_HEAD_ASSETS = _PREVIEW_HEAD_CORE + _THREE_JS_BOOTSTRAP

_CANVAS_BODY_MARKER = "__LEAGENT_CANVAS_BODY__"

# Full documents that own typography/layout via <style> (or a non-font stylesheet)
# must not receive the host Tailwind/Preflight shell — Preflight resets h1–h6 and
# the host body rules would override authored colours/backgrounds.
_AUTHORED_STYLE_MIN_CHARS = 80
_STYLE_BLOCK_RE = re.compile(r"(?is)<style\b[^>]*>(.*?)</style\s*>")
_LINK_TAG_RE = re.compile(r"(?is)<link\b[^>]*>")
_STYLESHEET_REL_RE = re.compile(r"""(?i)\brel\s*=\s*(['"]?)stylesheet\1""")
_HREF_ATTR_RE = re.compile(
    r"""(?ix)\bhref\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))"""
)
_FONT_STYLESHEET_HOSTS = frozenset(
    {
        "fonts.googleapis.com",
        "fonts.gstatic.com",
    }
)


def _authored_style_char_count(html: str) -> int:
    """Whitespace-collapsed length of inline ``<style>`` contents."""
    total = 0
    for match in _STYLE_BLOCK_RE.finditer(html or ""):
        total += len(re.sub(r"\s+", "", match.group(1) or ""))
    return total


def _has_non_font_stylesheet_link(html: str) -> bool:
    """True when a ``rel=stylesheet`` link targets a page-owned CSS file/CDN."""
    for match in _LINK_TAG_RE.finditer(html or ""):
        tag = match.group(0)
        if not _STYLESHEET_REL_RE.search(tag):
            continue
        href_m = _HREF_ATTR_RE.search(tag)
        href = (
            (href_m.group(1) or href_m.group(2) or href_m.group(3) or "")
            if href_m
            else ""
        ).strip().lower()
        if not href or href.startswith("data:"):
            continue
        if any(host in href for host in _FONT_STYLESHEET_HOSTS):
            continue
        return True
    return False


def document_has_authored_styles(html: str) -> bool:
    """Whether a full document already owns presentation CSS.

    Used to decide host shell injection. Tiny diagnostic ``<style>`` blocks
    (below ``_AUTHORED_STYLE_MIN_CHARS``) still receive the shell so bare
    utility-class pages keep working.
    """
    return (
        _authored_style_char_count(html) >= _AUTHORED_STYLE_MIN_CHARS
        or _has_non_font_stylesheet_link(html)
    )


def document_provides_tailwind(html: str) -> bool:
    """True when the HTML already loads the Tailwind Play CDN."""
    return "cdn.tailwindcss.com" in (html or "").lower()


def _should_inject_preview_shell(html: str) -> bool:
    """Inject host Tailwind/Inter/base only for bare / utility-oriented pages."""
    if document_provides_tailwind(html):
        return False
    if document_has_authored_styles(html):
        return False
    return True


def _insert_assets_in_document_head(html: str, assets: str) -> str:
    """Place ``assets`` inside ``<head>``, creating one when missing."""
    m = re.search(r"(?i)</head\s*>", html)
    if m:
        pos = m.start()
        return html[:pos] + "\n" + assets + "\n" + html[pos:]
    m2 = re.search(r"(?i)<head[^>]*>", html)
    if m2:
        pos = m2.end()
        return html[:pos] + "\n" + assets + "\n" + html[pos:]
    m3 = re.search(r"(?i)<html[^>]*>", html)
    if m3:
        pos = m3.end()
        return (
            html[:pos]
            + "\n<head>\n"
            + assets
            + "\n</head>\n"
            + html[pos:]
        )
    return html


def _wrap_html_fragment(body: str) -> str:
    """Wrap a body fragment in a full document with Tailwind + base styles."""
    head_assets = _preview_head_assets(body)
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8"/>\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>\n'
        f"{head_assets}\n"
        "</head>\n<body>\n"
        f"{_CANVAS_BODY_MARKER}\n"
        "</body>\n</html>"
    ).replace(_CANVAS_BODY_MARKER, body)


_CAMERA_LIFECYCLE_SCRIPT = """<script>
(function () {
  var active = new Set();
  function stopAll() {
    active.forEach(function (s) {
      s.getTracks().forEach(function (t) { t.stop(); });
    });
    active.clear();
    document.querySelectorAll("video,audio").forEach(function (el) {
      var so = el.srcObject;
      if (so && typeof so.getTracks === "function") {
        so.getTracks().forEach(function (t) { t.stop(); });
      }
      el.srcObject = null;
    });
  }
  window.__leagentReleaseMedia = stopAll;
  window.__leagentAttachCamera = function (video, constraints) {
    if (!video) return Promise.reject(new Error("video element required"));
    constraints = constraints || { video: { facingMode: "user" }, audio: false };
    return navigator.mediaDevices.getUserMedia(constraints).then(function (stream) {
      video.setAttribute("playsinline", "");
      video.setAttribute("autoplay", "");
      video.muted = true;
      video.srcObject = stream;
      var playPromise = video.play();
      if (playPromise && typeof playPromise.then === "function") {
        return playPromise.then(function () { return stream; });
      }
      return stream;
    });
  };
  window.addEventListener("pagehide", stopAll);
  window.addEventListener("beforeunload", stopAll);
  var md = navigator.mediaDevices;
  if (md && md.getUserMedia) {
    var orig = md.getUserMedia.bind(md);
    md.getUserMedia = function (constraints) {
      stopAll();
      return orig(constraints).then(function (stream) {
        active.add(stream);
        stream.getTracks().forEach(function (track) {
          track.addEventListener("ended", function () {
            if (stream.getTracks().every(function (t) { return t.readyState === "ended"; })) {
              active.delete(stream);
            }
          });
        });
        return stream;
      });
    };
  }
})();
</script>"""


def _inject_camera_lifecycle_script(html: str) -> str:
    """Release camera hardware on iframe unload; auto-stop stale streams before reuse."""
    if "__leagentReleaseMedia" in html:
        return html
    m = re.search(r"(?i)</head\s*>", html)
    if m:
        pos = m.start()
        return html[:pos] + _CAMERA_LIFECYCLE_SCRIPT + html[pos:]
    m2 = re.search(r"(?i)</body\s*>", html)
    if m2:
        pos = m2.start()
        return html[:pos] + _CAMERA_LIFECYCLE_SCRIPT + html[pos:]
    return html + _CAMERA_LIFECYCLE_SCRIPT


def _inject_preview_iframe_bootstrap(html: str) -> str:
    if "__leagentPreviewIframeBootstrap" in html:
        return html
    script = _PREVIEW_IFRAME_BOOTSTRAP.replace(
        "<script>",
        "<script>/* __leagentPreviewIframeBootstrap */",
        1,
    )
    m = re.search(r"(?i)</body\s*>", html)
    if m:
        pos = m.start()
        return html[:pos] + script + html[pos:]
    return html + script


def _inject_preview_assets_into_full_document(html: str) -> str:
    """Conditionally inject the host preview shell into a full HTML document.

    * Already loads Tailwind CDN → leave as-is (author owns the stack).
    * Substantial authored ``<style>`` / non-font stylesheet → leave as-is so
      Tailwind Preflight and host body resets cannot override page CSS.
    * Otherwise (bare shell / utility-class page) → inject Tailwind + Inter +
      base helpers + Three.js global when missing.
    """
    if "<html" not in (html or "").lower():
        return html
    if not _should_inject_preview_shell(html):
        return html
    return _insert_assets_in_document_head(html, _preview_head_assets(html))


def playwright_document_base(settings: Settings) -> str:
    """Origin Playwright uses to resolve ``/api/v1/...`` asset URLs in ``set_content``."""
    explicit = (settings.canvas.preview_public_base or "").strip().rstrip("/")
    if explicit:
        return explicit
    return f"http://127.0.0.1:{int(settings.port)}"


_WAIT_DOCUMENT_MEDIA_JS = """
async () => {
  try { await document.fonts.ready; } catch (e) {}
  const imgs = Array.from(document.images || []);
  await Promise.all(
    imgs.map((img) => {
      if (img.complete && img.naturalWidth > 0) return Promise.resolve();
      return new Promise((resolve) => {
        img.addEventListener("load", resolve, { once: true });
        img.addEventListener("error", resolve, { once: true });
        setTimeout(resolve, 15000);
      });
    }),
  );
}
"""


def canvas_preview_absolute_url(settings: Settings, token: str) -> str:
    """Full URL for Playwright to load the same HTML as the hosted canvas iframe."""
    return f"{playwright_document_base(settings).rstrip('/')}{preview_query_path(token)}"


async def load_html_in_playwright_page(
    page: Any,
    settings: Settings,
    *,
    html: str | None = None,
    navigate_url: str | None = None,
    wait_until: str = "load",
    timeout_ms: int = 30_000,
) -> None:
    """Load HTML in headless Chromium and wait for fonts/images.

    Use ``navigate_url`` (canvas preview) when relative ``/api/v1/files/...`` assets
    must resolve against the running API. Use ``html`` + absolute asset URLs for
    offline documents (e.g. GenUI PDF). Playwright's ``set_content`` has no ``url=``
    parameter on our supported version.
    """
    if navigate_url:
        await page.goto(navigate_url, wait_until=wait_until, timeout=timeout_ms)
    elif html is not None:
        await page.set_content(html, wait_until=wait_until, timeout=timeout_ms)
    else:
        raise ValueError("load_html_in_playwright_page requires html or navigate_url")
    try:
        await page.evaluate(_WAIT_DOCUMENT_MEDIA_JS)
    except Exception:
        pass
    await page.wait_for_timeout(200)


def build_preview_html(
    doc: CanvasDocument,
    settings: Settings,
    *,
    public_base: str | None = None,
    allow_js: bool = False,
) -> tuple[str, str]:
    """Return (html_body, content_type mime).

    Pass ``public_base`` when rendering offline (Playwright screenshot/PDF) so
    managed file preview URLs resolve against the running API origin.
    """
    from html import escape

    ct = doc.content_type
    if ct == CanvasContentType.EMBED_URL.value and doc.embed_url:
        safe = _validate_embed_url(
            doc.embed_url,
            allow_loopback=bool(settings.canvas.embed_allow_loopback),
        )
        esc = escape(safe, quote=True)
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/></head>
<body style="margin:0"><iframe src="{esc}" title="embed" style="width:100%;height:100vh;border:0"
 referrerpolicy="no-referrer-when-downgrade"
 sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"></iframe></body></html>"""
        return html, "text/html; charset=utf-8"
    if ct == CanvasContentType.GEN_UI_SNAPSHOT.value and doc.ui_snapshot_json:
        __import__("json").loads(doc.ui_snapshot_json)  # validate JSON
        safe = doc.ui_snapshot_json
        esc = escape(safe, quote=False)
        html = _wrap_html_fragment(
            f'<div class="max-w-3xl mx-auto">'
            f'<p class="text-sm text-gray-500 mb-4">Generative UI snapshot '
            f"(use the host app right panel for the interactive tree).</p>"
            f'<pre class="text-xs bg-gray-50 p-4 rounded-xl '
            f'overflow-auto whitespace-pre-wrap border border-gray-200">'
            f"{esc}</pre></div>",
        )
        return html, "text/html; charset=utf-8"
    body = doc.html_body or ""
    body = _inject_maps_key(body, (settings.canvas.google_maps_api_key or "").strip())
    body = sanitize_html(
        body,
        max_bytes=settings.canvas.max_html_bytes,
        allow_js=allow_js,
    )
    body = sign_managed_file_urls_in_html(
        body,
        settings=settings,
        user_id=doc.user_id,
        public_base=public_base,
    )
    if "<html" in body.lower():
        html = _inject_preview_assets_into_full_document(body)
    else:
        html = _wrap_html_fragment(body)
    if allow_js:
        html = _inject_camera_lifecycle_script(html)
        html = _inject_preview_iframe_bootstrap(html)
    return html, "text/html; charset=utf-8"


class CanvasService:
    """Canvas persistence + preview token helpers."""

    def __init__(
        self,
        settings: Settings,
        db: DatabaseService,
        chat: ChatService | None = None,
    ) -> None:
        self._settings = settings
        self._db = db
        self._chat = chat

    async def _assert_session(self, user_id: UUID, session_id: UUID) -> ChatSession:
        if self._chat is None:
            raise RuntimeError("ChatService required for canvas session checks")
        session = await self._chat.get_session(session_id, user_id=user_id)
        if session is None:
            raise PermissionError("session not found or denied")
        return session

    async def publish_revision(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        title: str,
        mode: str,
        html: str | None = None,
        html_files: dict[str, str] | None = None,
        html_bundle_entry: str | None = None,
        embed_url: str | None = None,
        ui_snapshot: dict[str, Any] | None = None,
        message_id: UUID | None = None,
        canvas_id: UUID | None = None,
    ) -> dict[str, Any]:
        await self._assert_session(user_id, session_id)

        cid = canvas_id or uuid4()
        async with self._db.session() as db:
            res = await db.execute(
                select(func.max(CanvasDocument.revision)).where(CanvasDocument.canvas_id == cid),
            )
            max_rev = res.scalar_one()
            next_rev = int(max_rev or 0) + 1

            if mode == "embed_url":
                if not embed_url:
                    raise ValueError("embed_url required for embed_url mode")
                _validate_embed_url(
                    embed_url,
                    allow_loopback=bool(self._settings.canvas.embed_allow_loopback),
                )
                content_type = CanvasContentType.EMBED_URL.value
                html_body = None
                ui_json = None
                emb = embed_url
            elif mode == "gen_ui":
                if not ui_snapshot:
                    raise ValueError("ui_snapshot required for gen_ui mode")
                normalized = validate_ui_tree(
                    ui_snapshot,
                    max_depth=self._settings.canvas.max_tree_depth,
                    max_nodes=self._settings.canvas.max_nodes_per_tree,
                )
                raw = __import__("json").dumps(normalized, ensure_ascii=False)
                if len(raw.encode("utf-8")) > self._settings.canvas.max_ui_snapshot_bytes:
                    raise ValueError("ui_snapshot too large")
                content_type = CanvasContentType.GEN_UI_SNAPSHOT.value
                html_body = None
                emb = None
                ui_json = raw
            else:
                html_out: str | None = None
                if html_files is not None and len(html_files) > 0:
                    if html and html.strip():
                        raise ValueError("Pass either `html` or `html_files`, not both")
                    entry_raw = (html_bundle_entry or "").strip() or None
                    html_out = merge_html_files_to_document(
                        entry=entry_raw,
                        files=html_files,
                        max_output_bytes=self._settings.canvas.max_html_bytes,
                    )
                elif html and html.strip():
                    html_out = html
                if not html_out or not html_out.strip():
                    raise ValueError(
                        "html mode requires non-empty `html`, or `html_files` "
                        "(entry auto-resolved when omitted / sole HTML file)",
                    )
                content_type = CanvasContentType.HTML.value
                # Store raw HTML; sanitisation runs at preview time (js=0/1).
                if len(html_out.encode("utf-8")) > self._settings.canvas.max_html_bytes:
                    raise ValueError(
                        f"HTML exceeds max size ({self._settings.canvas.max_html_bytes} bytes)",
                    )
                html_body = html_out
                emb = None
                ui_json = None

            session_row = await db.get(ChatSession, session_id)
            ws_id = getattr(session_row, "workspace_id", None) if session_row else None

            row = CanvasDocument(
                id=uuid4(),
                canvas_id=cid,
                revision=next_rev,
                session_id=session_id,
                user_id=user_id,
                workspace_id=ws_id,
                message_id=message_id,
                title=title[:500],
                content_type=content_type,
                html_body=html_body,
                embed_url=emb,
                ui_snapshot_json=ui_json,
            )
            db.add(row)
            await db.flush()
            await db.refresh(row)

        token = mint_preview_token(
            self._settings,
            canvas_id=cid,
            revision=next_rev,
            user_id=user_id,
        )
        path = preview_query_path(token)
        return {
            "canvas_id": str(cid),
            "revision": next_rev,
            "preview_path": path,
            "title": title,
            "content_type": content_type,
            "trust": "hosted",
        }

    async def list_session_latest_documents(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
    ) -> list[dict[str, Any]]:
        """Latest revision per canvas in a chat session, with fresh preview token paths."""
        await self._assert_session(user_id, session_id)
        async with self._db.session() as db:
            stmt = (
                select(CanvasDocument)
                .where(CanvasDocument.session_id == session_id)
                .where(CanvasDocument.user_id == user_id)
                .order_by(col(CanvasDocument.canvas_id).asc(), col(CanvasDocument.revision).desc())
            )
            res = await db.execute(stmt)
            rows = list(res.scalars().all())
        picked: dict[UUID, CanvasDocument] = {}
        for r in rows:
            if r.canvas_id not in picked:
                picked[r.canvas_id] = r
        out: list[dict[str, Any]] = []
        for doc in picked.values():
            token = mint_preview_token(
                self._settings,
                canvas_id=doc.canvas_id,
                revision=doc.revision,
                user_id=user_id,
            )
            path = preview_query_path(token)
            cid = str(doc.canvas_id)
            out.append(
                {
                    "id": f"{cid}-{doc.revision}" if cid and doc.revision else str(doc.id),
                    "canvas_id": cid,
                    "revision": doc.revision,
                    "title": doc.title,
                    "content_type": doc.content_type,
                    "preview_path": path,
                    "message_id": str(doc.message_id) if doc.message_id else None,
                    "trust": "hosted",
                },
            )
        return out

    async def get_latest_document(
        self,
        *,
        user_id: UUID,
        canvas_id: UUID,
    ) -> CanvasDocument | None:
        async with self._db.session() as db:
            stmt = (
                select(CanvasDocument)
                .where(CanvasDocument.canvas_id == canvas_id)
                .where(CanvasDocument.user_id == user_id)
                .order_by(col(CanvasDocument.revision).desc())
                .limit(1)
            )
            res = await db.execute(stmt)
            return res.scalar_one_or_none()

    async def get_revision(
        self,
        *,
        user_id: UUID,
        canvas_id: UUID,
        revision: int,
    ) -> CanvasDocument | None:
        async with self._db.session() as db:
            stmt = select(CanvasDocument).where(
                CanvasDocument.canvas_id == canvas_id,
                CanvasDocument.revision == revision,
                CanvasDocument.user_id == user_id,
            )
            res = await db.execute(stmt)
            return res.scalar_one_or_none()

    async def fetch_for_preview(
        self,
        *,
        canvas_id: UUID,
        revision: int,
        user_id: UUID,
    ) -> CanvasDocument | None:
        async with self._db.session() as db:
            stmt = select(CanvasDocument).where(
                CanvasDocument.canvas_id == canvas_id,
                CanvasDocument.revision == revision,
                CanvasDocument.user_id == user_id,
            )
            res = await db.execute(stmt)
            return res.scalar_one_or_none()

    async def load_verified_from_token(self, token: str) -> CanvasDocument | None:
        try:
            claims = decode_preview_token(self._settings, token)
        except TokenError as e:
            logger.info("canvas_preview_token_invalid", error=str(e))
            return None
        try:
            cid = UUID(str(claims.get("cid")))
            rev = int(claims.get("rev"))
            uid = UUID(str(claims.get("sub")))
        except (TypeError, ValueError):
            return None
        return await self.fetch_for_preview(canvas_id=cid, revision=rev, user_id=uid)


_canvas_service: CanvasService | None = None


def get_canvas_service() -> CanvasService:
    if _canvas_service is None:
        raise RuntimeError("CanvasService not initialized")
    return _canvas_service


async def init_canvas_service(
    settings: Settings,
    db: DatabaseService,
    chat: ChatService | None = None,
) -> CanvasService:
    global _canvas_service
    _canvas_service = CanvasService(settings, db, chat=chat)
    return _canvas_service
