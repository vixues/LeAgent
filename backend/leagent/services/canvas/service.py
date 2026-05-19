"""Persist canvas revisions, mint preview tokens, and serve HTML."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlmodel import col, func, select

from leagent.services.auth.tokens import mint_token, decode_token, TokenError

from leagent.services.canvas.html_bundle import merge_html_files_to_document
from leagent.services.database.models.canvas import CanvasContentType, CanvasDocument
from leagent.services.database.models.message import ChatSession
from leagent.services.gen_ui.schema import validate_ui_tree, ui_tree_from_json_bytes

if TYPE_CHECKING:
    from leagent.config.settings import Settings
    from leagent.services.chat.service import ChatService
    from leagent.services.database.service import DatabaseService

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


# --- HTML sanitisation ----------------------------------------------------
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

_SCRIPT_SRC_ALLOWLIST: tuple[str, ...] = (
    "cdn.tailwindcss.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
)

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


def sanitize_html(html: str, *, max_bytes: int) -> str:
    """Sanitise agent-supplied HTML for safe hosted preview.

    Two paths:
      * Full <!DOCTYPE html> docs — narrow scrubber that keeps <head>,
        <body>, <style>, class/style attrs, SVG.
      * Body fragments — nh3.Cleaner with a relaxed allowlist that keeps
        Tailwind utility classes and inline styles.
    """
    raw = html or ""
    if len(raw.encode("utf-8")) > max_bytes:
        raise ValueError(f"HTML exceeds max size ({max_bytes} bytes)")
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
_PREVIEW_HEAD_ASSETS = """
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
  darkMode: 'media',
}
</script>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; height: 100%; }
  body {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    color: #1a1a2e;
    background: #ffffff;
    line-height: 1.6;
    padding: 24px;
    min-height: 100%;
  }
  body::-webkit-scrollbar { width: 0; height: 0; }
  body { scrollbar-width: none; }
  @media (prefers-color-scheme: dark) {
    body { background: #0f0f1a; color: #f8fafc; }
  }
  img { max-width: 100%; height: auto; }
  a { color: #0284c7; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .wa-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
  .wa-gradient { background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%); color: #fff; }
  .wa-gradient-warm { background: linear-gradient(135deg, #f97316 0%, #ec4899 100%); color: #fff; }
  .wa-gradient-fresh { background: linear-gradient(135deg, #10b981 0%, #0ea5e9 100%); color: #fff; }
  @media (prefers-color-scheme: dark) {
    .wa-card { background: #1a1a2e; border-color: #334155; }
  }
</style>
"""

_CANVAS_BODY_MARKER = "__LEAGENT_CANVAS_BODY__"


def _wrap_html_fragment(body: str) -> str:
    """Wrap a body fragment in a full document with Tailwind + base styles."""
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8"/>\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>\n'
        f"{_PREVIEW_HEAD_ASSETS}\n"
        "</head>\n<body>\n"
        f"{_CANVAS_BODY_MARKER}\n"
        "</body>\n</html>"
    ).replace(_CANVAS_BODY_MARKER, body)


def _inject_preview_assets_into_full_document(html: str) -> str:
    """When the agent returns a full <!DOCTYPE html>… doc, it often omits Tailwind; inject ours."""
    low = html.lower()
    if "<html" not in low:
        return html
    if "cdn.tailwindcss.com" in low:
        return html
    m = re.search(r"(?i)</head\s*>", html)
    if m:
        pos = m.start()
        return html[:pos] + "\n" + _PREVIEW_HEAD_ASSETS + "\n" + html[pos:]
    m2 = re.search(r"(?i)<head[^>]*>", html)
    if m2:
        pos = m2.end()
        return html[:pos] + "\n" + _PREVIEW_HEAD_ASSETS + "\n" + html[pos:]
    m3 = re.search(r"(?i)<html[^>]*>", html)
    if m3:
        pos = m3.end()
        return (
            html[:pos]
            + "\n<head>\n"
            + _PREVIEW_HEAD_ASSETS
            + "\n</head>\n"
            + html[pos:]
        )
    return html


def build_preview_html(doc: CanvasDocument, settings: Settings) -> tuple[str, str]:
    """Return (html_body, content_type mime)."""
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
            f'<pre class="text-xs bg-gray-50 dark:bg-gray-800 p-4 rounded-xl '
            f'overflow-auto whitespace-pre-wrap border border-gray-200 dark:border-gray-700">'
            f"{esc}</pre></div>",
        )
        return html, "text/html; charset=utf-8"
    body = doc.html_body or ""
    body = _inject_maps_key(body, (settings.canvas.google_maps_api_key or "").strip())
    body = sanitize_html(body, max_bytes=settings.canvas.max_html_bytes)
    if "<html" in body.lower():
        return _inject_preview_assets_into_full_document(body), "text/html; charset=utf-8"
    wrapped = _wrap_html_fragment(body)
    return wrapped, "text/html; charset=utf-8"


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
                    entry = (html_bundle_entry or "index.html").strip()
                    html_out = merge_html_files_to_document(
                        entry=entry,
                        files=html_files,
                        max_output_bytes=self._settings.canvas.max_html_bytes,
                    )
                elif html and html.strip():
                    html_out = html
                if not html_out or not html_out.strip():
                    raise ValueError(
                        "html mode requires non-empty `html`, or `html_files` plus `html_bundle_entry`",
                    )
                content_type = CanvasContentType.HTML.value
                html_body = sanitize_html(
                    html_out,
                    max_bytes=self._settings.canvas.max_html_bytes,
                )
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
