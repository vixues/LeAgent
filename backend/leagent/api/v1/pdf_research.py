"""PDF Research Mode API.

Synchronous, reader-facing endpoints that power the PDF Pro Reader's Research
Paper Mode: structure/outline extraction, section/paper summarization,
reference extraction, and text/region translation. These complement the
agent-facing tools in :mod:`leagent.tools.doc.pdf_research` (same core logic),
serving the cases where the UI needs an immediate answer without a full agent
turn.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from leagent.api.v1.files import _resolve_file_for_serve
from leagent.db import DatabaseService, get_database_service
from leagent.services.auth import CurrentUserId
from leagent.tools.doc.pdf_research_core import (
    extract_citations,
    extract_formula_candidates,
    extract_page_text,
    extract_pages_text_tagged,
    extract_region_text,
    extract_structure,
)
from leagent.tools.doc.pdf_research import (
    build_formula_extraction_prompt,
    build_summary_prompt,
    build_translate_prompt,
    parse_formula_json,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_SUMMARY_CHAR_BUDGET = 16_000
_TRANSLATE_CHAR_BUDGET = 8_000
_FORMULA_CHAR_BUDGET = 24_000


# --------------------------------------------------------------------------- #
# Request / response models
# --------------------------------------------------------------------------- #


class StructureRequest(BaseModel):
    pass


class SummaryRequest(BaseModel):
    start_page: int | None = Field(default=None, ge=1)
    end_page: int | None = Field(default=None, ge=1)
    section_title: str | None = None
    target_lang: str | None = None
    model_provider: str | None = None
    model_name: str | None = None


class CitationsRequest(BaseModel):
    pass


class TranslateRequest(BaseModel):
    text: str | None = None
    file_id: UUID | None = None
    page: int | None = Field(default=None, ge=1)
    bbox: list[float] | None = None
    target_lang: str = "en"
    model_provider: str | None = None
    model_name: str | None = None


class FormulasRequest(BaseModel):
    model_provider: str | None = None
    model_name: str | None = None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _pdf_path(file_id: UUID, user_id: UUID, db: DatabaseService) -> str:
    file = await _resolve_file_for_serve(
        file_id,
        token=None,
        jwt_user_id=user_id,
        required_scope="preview",
        db=db,
    )
    name = (file.original_name or "").lower()
    mime = (file.mime_type or "").lower()
    if not (name.endswith(".pdf") or mime == "application/pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not a PDF",
        )
    return file.storage_path


async def _complete(
    prompt: str,
    *,
    max_tokens: int,
    model_provider: str | None = None,
    model_name: str | None = None,
) -> str:
    """Run a single LLM completion for reader-side summary/translation."""
    from leagent.llm import ChatMessage
    from leagent.llm import MessageRole as LLMMessageRole
    from leagent.main import get_service_manager

    sm = get_service_manager()
    llm = sm.llm_service if sm else None
    if llm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service unavailable",
        )
    messages = [ChatMessage(role=LLMMessageRole.USER, content=prompt)]
    try:
        response = await llm.complete(
            messages,
            temperature=0.2,
            max_tokens=max_tokens,
            provider=(model_provider or "").strip() or None,
            model=(model_name or "").strip() or None,
        )
    except Exception as exc:  # noqa: BLE001 - provider/network errors
        logger.warning("pdf_llm_complete_failed error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM request failed (check provider/network configuration).",
        ) from exc
    return (response.content or "").strip()


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@router.post("/{file_id}/structure")
async def pdf_structure(
    file_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> dict:
    """Return page count, title, outline, sections, and figures/tables."""
    path = await _pdf_path(file_id, user_id, db)
    try:
        return extract_structure(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pdf_structure_failed file_id=%s error=%s", file_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not analyze PDF: {exc}",
        ) from exc


@router.post("/{file_id}/citations")
async def pdf_citations(
    file_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> dict:
    """Extract the reference / bibliography list."""
    path = await _pdf_path(file_id, user_id, db)
    try:
        citations = extract_citations(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pdf_citations_failed file_id=%s error=%s", file_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not extract citations: {exc}",
        ) from exc
    return {"citations": citations}


@router.post("/{file_id}/summary")
async def pdf_summary(
    file_id: UUID,
    body: SummaryRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> dict:
    """Summarize a page range (or whole paper) with the LLM."""
    path = await _pdf_path(file_id, user_id, db)
    try:
        text = extract_page_text(path, body.start_page, body.end_page)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not read PDF text: {exc}",
        ) from exc
    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No extractable text (the PDF may be scanned; OCR required).",
        )
    prompt = build_summary_prompt(
        text[:_SUMMARY_CHAR_BUDGET],
        section_title=body.section_title,
        target_lang=body.target_lang,
    )
    summary = await _complete(
        prompt,
        max_tokens=800,
        model_provider=body.model_provider,
        model_name=body.model_name,
    )
    return {"summary": summary, "section_title": body.section_title}


@router.post("/{file_id}/formulas")
async def pdf_formulas(
    file_id: UUID,
    body: FormulasRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> dict:
    """Extract every distinct equation as renderable LaTeX (LLM-assisted)."""
    path = await _pdf_path(file_id, user_id, db)
    try:
        text = extract_pages_text_tagged(path, char_budget=_FORMULA_CHAR_BUDGET)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not read PDF text: {exc}",
        ) from exc
    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No extractable text (the PDF may be scanned; OCR required).",
        )
    formulas: list[dict] = []
    source = "ai"
    prompt = build_formula_extraction_prompt(text)
    try:
        raw = await _complete(
            prompt,
            max_tokens=2400,
            model_provider=body.model_provider,
            model_name=body.model_name,
        )
        formulas = parse_formula_json(raw)
    except Exception as exc:  # noqa: BLE001 - LLM/network failure → heuristic fallback
        logger.warning("pdf_formulas_llm_failed file_id=%s error=%s", file_id, exc)
    # If the LLM is unreachable or returned nothing usable, degrade gracefully to
    # a heuristic, LLM-free scan so the Formulas tab still has content.
    if not formulas:
        try:
            formulas = extract_formula_candidates(path)
            source = "heuristic"
        except Exception as exc:  # noqa: BLE001
            logger.warning("pdf_formulas_heuristic_failed file_id=%s error=%s", file_id, exc)
            formulas = []
    return {"formulas": formulas, "source": source}


@router.post("/translate")
async def pdf_translate(
    body: TranslateRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> dict:
    """Translate free text, or a PDF page region (file_id + page + bbox)."""
    source = (body.text or "").strip()
    if not source and body.file_id and body.page and body.bbox:
        if len(body.bbox) != 4:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="bbox must be [x0, y0, x1, y1]",
            )
        path = await _pdf_path(body.file_id, user_id, db)
        try:
            source = extract_region_text(
                path, body.page, (body.bbox[0], body.bbox[1], body.bbox[2], body.bbox[3])
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Could not read region: {exc}",
            ) from exc
    if not source.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No text to translate (region may be image-only).",
        )
    prompt = build_translate_prompt(source[:_TRANSLATE_CHAR_BUDGET], body.target_lang)
    translated = await _complete(
        prompt,
        max_tokens=1200,
        model_provider=body.model_provider,
        model_name=body.model_name,
    )
    return {
        "source_text": source,
        "translated_text": translated,
        "target_lang": body.target_lang,
    }
