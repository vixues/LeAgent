"""Canvas publish API + signed HTML preview."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from urllib.parse import quote
from uuid import UUID  # noqa: TC003 — FastAPI/Pydantic resolve route and model hints at runtime.

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from leagent.config.settings import get_settings
from leagent.services.auth import CurrentUserId  # noqa: TC001
from leagent.services.canvas.service import (
    CanvasService,
    build_preview_html,
    get_canvas_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _ascii_filename_fallback(name: str, *, default: str = "download") -> str:
    """Legacy ``filename=`` token must be latin-1; strip non-ASCII to underscores."""
    out = "".join(
        c if ord(c) < 128 and (c.isalnum() or c in "._- ") else "_" for c in name
    )
    return (out.strip("._ ") or default)[:180]


def _content_disposition(disposition: str, filename: str) -> str:
    """Build a latin-1-safe Content-Disposition with RFC 5987 ``filename*``."""
    disp = disposition if disposition in ("inline", "attachment") else "inline"
    ascii_name = _ascii_filename_fallback(filename)
    utf8_star = quote(filename, safe="")
    return f'{disp}; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_star}'


def _canvas_dep() -> CanvasService:
    try:
        return get_canvas_service()
    except RuntimeError as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canvas service unavailable",
        ) from e


CanvasDep = Annotated[CanvasService, Depends(_canvas_dep)]


class CanvasPublishRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    session_id: UUID
    mode: str = Field(..., pattern="^(html|embed_url|gen_ui)$")
    html: str | None = None
    html_files: dict[str, str] | None = None
    html_bundle_entry: str | None = Field(
        default=None,
        description="Entry path when using html_files (default index.html).",
    )
    embed_url: str | None = None
    ui_snapshot: dict[str, Any] | None = None
    message_id: UUID | None = None
    canvas_id: UUID | None = None
    open_in_panel: bool = True


class CanvasPublishResponse(BaseModel):
    canvas_id: str
    revision: int
    preview_path: str
    preview_url: str | None = None
    title: str
    content_type: str
    trust: str = "hosted"
    open_in_panel: bool = True


@router.post("", response_model=CanvasPublishResponse)
async def publish_canvas(
    body: CanvasPublishRequest,
    user_id: CurrentUserId,
    canvas: CanvasDep,
) -> CanvasPublishResponse:
    settings = get_settings()
    try:
        out = await canvas.publish_revision(
            user_id=user_id,
            session_id=body.session_id,
            title=body.title,
            mode=body.mode,
            html=body.html,
            html_files=body.html_files,
            html_bundle_entry=body.html_bundle_entry,
            embed_url=body.embed_url,
            ui_snapshot=body.ui_snapshot,
            message_id=body.message_id,
            canvas_id=body.canvas_id,
        )
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    base = (settings.canvas.preview_public_base or "").rstrip("/")
    preview_url = f"{base}{out['preview_path']}" if base else None
    return CanvasPublishResponse(
        canvas_id=out["canvas_id"],
        revision=out["revision"],
        preview_path=out["preview_path"],
        preview_url=preview_url,
        title=out["title"],
        content_type=out["content_type"],
        trust=out.get("trust", "hosted"),
        open_in_panel=body.open_in_panel,
    )


class CanvasRevisionRead(BaseModel):
    id: str
    canvas_id: str
    revision: int
    title: str
    content_type: str
    created_at: str


class CanvasSessionArtifactRead(BaseModel):
    """One canvas (latest revision) in a chat session, with a fresh preview path for replay."""

    id: str
    canvas_id: str
    revision: int
    title: str
    content_type: str
    preview_path: str
    message_id: str | None = None
    trust: str = "hosted"


class GenUiExportPdfRequest(BaseModel):
    """Validated gen UI tree → PDF bytes (Playwright)."""

    session_id: UUID | None = None
    message_id: UUID | None = None
    tree: dict[str, Any]
    mode: Literal["deck", "document"] = "document"
    page_size: Literal["A4", "Letter", "Slide16x9"] = "A4"
    orientation: Literal["portrait", "landscape"] = "portrait"


# Static paths must be registered before `/{canvas_id}` so "preview" is not parsed as a UUID.
@router.get("/by-session/{session_id}", response_model=list[CanvasSessionArtifactRead])
async def list_session_canvas_artifacts(
    session_id: UUID,
    user_id: CurrentUserId,
    canvas: CanvasDep,
) -> list[CanvasSessionArtifactRead]:
    """List latest canvas revision per canvas_id for replay after reload or history navigation."""
    rows = await canvas.list_session_latest_documents(user_id=user_id, session_id=session_id)
    return [CanvasSessionArtifactRead(**r) for r in rows]


@router.get("/preview", response_class=HTMLResponse)
async def preview_canvas(
    canvas: CanvasDep,
    token: str = Query(..., min_length=10),
) -> HTMLResponse:
    settings = get_settings()
    doc = await canvas.load_verified_from_token(token)
    if doc is None:
        return HTMLResponse(
            "<!DOCTYPE html><html><body>Invalid or expired preview token.</body></html>",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    html, _mime = build_preview_html(doc, settings)
    csp = settings.canvas.preview_csp.strip()
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }
    if csp:
        headers["Content-Security-Policy"] = csp
    return HTMLResponse(content=html, status_code=200, headers=headers)


@router.get("/preview/csp.txt", response_class=PlainTextResponse)
async def preview_csp_reference() -> PlainTextResponse:
    """Operator hint: tune CANVAS_PREVIEW_CSP for new third-party domains."""
    return PlainTextResponse(get_settings().canvas.preview_csp)


_pw_browser: Any = None
_pw_lock: Any = None


def _pdf_viewport(page_size: str, orientation: str) -> dict[str, int]:
    """Logical viewport before PDF (stabilizes layout; matches common paper pixels at 96dpi)."""
    if page_size == "Slide16x9":
        return {"width": 1280, "height": 720}
    land = orientation == "landscape"
    if page_size == "Letter":
        return {"width": 1056, "height": 816} if land else {"width": 816, "height": 1056}
    # A4
    return {"width": 1123, "height": 794} if land else {"width": 794, "height": 1123}


async def _get_pw_browser() -> Any:
    """Lazy-init a shared Playwright Chromium browser instance."""
    global _pw_browser, _pw_lock
    if _pw_lock is None:
        import asyncio
        _pw_lock = asyncio.Lock()
    async with _pw_lock:
        if _pw_browser is None or not _pw_browser.is_connected():
            try:
                from playwright.async_api import async_playwright
                pw = await async_playwright().start()
                _pw_browser = await pw.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--use-gl=swiftshader",
                    ],
                )
            except Exception as exc:
                logger.warning("playwright_browser_launch_failed: %s", exc, exc_info=True)
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Screenshot service unavailable (Playwright not installed)",
                ) from exc
        return _pw_browser


@router.get("/preview/screenshot")
async def screenshot_canvas(
    canvas: CanvasDep,
    token: str = Query(..., min_length=10),
    width: int = Query(default=800, ge=320, le=3840),
    height: int = Query(default=600, ge=240, le=2160),
    fmt: str = Query(default="png", alias="format", pattern="^(png|jpeg)$"),
) -> Response:
    """Render a canvas preview to an image using headless Chromium."""
    settings = get_settings()
    doc = await canvas.load_verified_from_token(token)
    if doc is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid or expired preview token")
    html, _mime = build_preview_html(doc, settings)

    browser = await _get_pw_browser()
    page = await browser.new_page(viewport={"width": width, "height": height})
    try:
        # Match PDF export: "load" is reliable with Tailwind CDN; networkidle often times out.
        await page.set_content(html, wait_until="load", timeout=30_000)
        try:
            await page.evaluate("() => document.fonts.ready")
        except Exception:
            pass
        await page.wait_for_timeout(300)
        screenshot_bytes = await page.screenshot(
            type=fmt,
            full_page=True,
            timeout=15_000,
        )
    except Exception as exc:
        logger.warning("canvas_preview_screenshot_failed: %s", exc, exc_info=True)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Screenshot render failed",
        ) from exc
    finally:
        await page.close()

    media_type = "image/png" if fmt == "png" else "image/jpeg"
    title = (doc.title or "canvas").strip()[:120] or "canvas"
    download_name = f"{title}.{fmt}"
    return Response(
        content=screenshot_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": _content_disposition("inline", download_name),
            "Cache-Control": "private, max-age=300",
        },
    )


@router.post("/genui/export/pdf")
async def genui_export_pdf(
    body: GenUiExportPdfRequest,
    _user_id: CurrentUserId,
) -> Response:
    """Render a validated GenUi tree to PDF using Chromium (print CSS, margins, optional outlines).

    Uses ``emulate_media('print')``, structured ``page.pdf`` margins / footer for document formats,
    and a typography-focused stylesheet — not a bare screen snapshot.
    """
    from jsonschema.exceptions import ValidationError

    from leagent.services.gen_ui.print_renderer import render_print_document_html
    from leagent.services.gen_ui.schema import validate_ui_tree
    from leagent.tools.canvas import get_canvas_settings

    settings = get_canvas_settings()
    try:
        normalized = validate_ui_tree(
            body.tree,
            max_depth=settings["max_tree_depth"],
            max_nodes=settings["max_nodes_per_tree"],
        )
    except ValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    html_doc = render_print_document_html(
        normalized,
        mode=body.mode,
        page_size=body.page_size,
    )

    browser = await _get_pw_browser()
    viewport = _pdf_viewport(body.page_size, body.orientation)
    page = await browser.new_page(viewport=viewport)
    try:
        await page.set_content(html_doc, wait_until="load", timeout=30_000)
        try:
            await page.evaluate("() => document.fonts.ready")
        except Exception:
            pass
        await page.wait_for_timeout(150)
        # Use print CSS cascade (typography, @page) — not screen snapshot scaling.
        await page.emulate_media(media="print")

        pdf_kwargs: dict[str, Any] = {"print_background": True}
        if body.page_size == "Slide16x9":
            dims = await page.evaluate(
                """() => {
                    const de = document.documentElement;
                    const b = document.body;
                    return {
                        h: Math.max(de.scrollHeight, b ? b.scrollHeight : 0),
                        w: Math.max(de.scrollWidth, b ? b.scrollWidth : 0),
                    };
                }"""
            )
            try:
                h_px = max(720, int(dims.get("h", 720)))
                w_px = max(1280, int(dims.get("w", 1280)))
            except (TypeError, ValueError):
                h_px, w_px = 720, 1280
            h_px = min(h_px, 32000)
            w_px = min(w_px, 32000)
            await page.set_viewport_size({"width": w_px, "height": h_px})
            pdf_kwargs.update(
                {
                    "width": f"{w_px}px",
                    "height": f"{h_px}px",
                    "margin": {"top": "0", "right": "0", "bottom": "0", "left": "0"},
                    "prefer_css_page_size": False,
                    "outline": True,
                    "tagged": True,
                }
            )
        else:
            fmt = "Letter" if body.page_size == "Letter" else "A4"
            pdf_kwargs.update(
                {
                    "format": fmt,
                    "landscape": body.orientation == "landscape",
                    "prefer_css_page_size": False,
                    "margin": {
                        "top": "12mm",
                        "bottom": "20mm",
                        "left": "14mm",
                        "right": "14mm",
                    },
                    "display_header_footer": True,
                    "footer_template": (
                        '<div style="width:100%;font-size:9px;color:#64748b;'
                        'text-align:center;font-family:ui-sans-serif,system-ui,sans-serif;padding:0;">'
                        '<span class="pageNumber"></span>'
                        '<span style="margin:0 0.35em;color:#cbd5e1">·</span>'
                        "<span class=\"totalPages\"></span>"
                        "</div>"
                    ),
                    "outline": True,
                    "tagged": True,
                }
            )
        pdf_bytes = await page.pdf(**pdf_kwargs)
    finally:
        await page.close()

    fname = f"genui-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


class GenUiExportDocxRequest(BaseModel):
    """Validated gen UI tree → DOCX bytes."""

    session_id: UUID | None = None
    message_id: UUID | None = None
    tree: dict[str, Any]
    mode: Literal["deck", "document"] = "document"


class GenUiExportPptxRequest(BaseModel):
    """Validated gen UI tree → PPTX bytes."""

    session_id: UUID | None = None
    message_id: UUID | None = None
    tree: dict[str, Any]
    slide_width_inches: float = 13.333
    slide_height_inches: float = 7.5


@router.post("/genui/export/docx")
async def genui_export_docx(
    body: GenUiExportDocxRequest,
    _user_id: CurrentUserId,
) -> Response:
    """Render a validated GenUi tree to a Word document (.docx)."""
    from jsonschema.exceptions import ValidationError

    from leagent.services.gen_ui.docx_renderer import render_genui_to_docx
    from leagent.services.gen_ui.schema import validate_ui_tree
    from leagent.tools.canvas import get_canvas_settings

    settings = get_canvas_settings()
    try:
        normalized = validate_ui_tree(
            body.tree,
            max_depth=settings["max_tree_depth"],
            max_nodes=settings["max_nodes_per_tree"],
        )
    except ValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    docx_bytes = render_genui_to_docx(normalized, mode=body.mode)

    fname = f"genui-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/genui/export/pptx")
async def genui_export_pptx(
    body: GenUiExportPptxRequest,
    _user_id: CurrentUserId,
) -> Response:
    """Render a validated GenUi SlideDeck tree to a PowerPoint presentation (.pptx)."""
    from jsonschema.exceptions import ValidationError

    from leagent.services.gen_ui.pptx_renderer import render_genui_to_pptx
    from leagent.services.gen_ui.schema import validate_ui_tree
    from leagent.tools.canvas import get_canvas_settings

    settings = get_canvas_settings()
    try:
        normalized = validate_ui_tree(
            body.tree,
            max_depth=settings["max_tree_depth"],
            max_nodes=settings["max_nodes_per_tree"],
        )
    except ValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    pptx_bytes = render_genui_to_pptx(
        normalized,
        slide_width_inches=body.slide_width_inches,
        slide_height_inches=body.slide_height_inches,
    )

    fname = f"genui-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.pptx"
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/{canvas_id}/revisions", response_model=list[CanvasRevisionRead])
async def list_revisions(
    canvas_id: UUID,
    user_id: CurrentUserId,
    canvas: CanvasDep,
) -> list[CanvasRevisionRead]:
    from sqlmodel import col, select

    from leagent.main import get_service_manager

    sm = get_service_manager()
    if sm.db is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
    from leagent.services.database.models.canvas import CanvasDocument

    async with sm.db.session() as db:
        stmt = (
            select(CanvasDocument)
            .where(CanvasDocument.canvas_id == canvas_id, CanvasDocument.user_id == user_id)
            .order_by(col(CanvasDocument.revision).asc())
        )
        res = await db.execute(stmt)
        rows = list(res.scalars().all())
    return [
        CanvasRevisionRead(
            id=str(r.id),
            canvas_id=str(r.canvas_id),
            revision=r.revision,
            title=r.title,
            content_type=r.content_type,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]


@router.get("/{canvas_id}", response_model=CanvasRevisionRead)
async def get_canvas_latest(
    canvas_id: UUID,
    user_id: CurrentUserId,
    canvas: CanvasDep,
) -> CanvasRevisionRead:
    doc = await canvas.get_latest_document(user_id=user_id, canvas_id=canvas_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Canvas not found")
    return CanvasRevisionRead(
        id=str(doc.id),
        canvas_id=str(doc.canvas_id),
        revision=doc.revision,
        title=doc.title,
        content_type=doc.content_type,
        created_at=doc.created_at.isoformat() if doc.created_at else "",
    )
