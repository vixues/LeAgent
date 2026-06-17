import { apiClient } from '@/api/client';
import { getComposerModelMode } from '@/stores/chatDraft';
import type {
  PdfCitationsResponse,
  PdfFormulasResponse,
  PdfStructureResponse,
  PdfSummaryResponse,
  PdfTranslateResponse,
} from '../types';

function getPdfModelSelection(): { model_provider?: string; model_name?: string } {
  const mode = getComposerModelMode();
  if (!mode) return {};
  const slash = mode.indexOf('/');
  if (slash <= 0) return {};
  const provider = mode.slice(0, slash).trim();
  const name = mode.slice(slash + 1).trim();
  if (!provider || !name) return {};
  return { model_provider: provider, model_name: name };
}

/** Outline + heuristic sections + figures/tables for the research sidebar. */
export function fetchPdfStructure(fileId: string): Promise<PdfStructureResponse> {
  return apiClient.post<PdfStructureResponse>(`/pdf/${fileId}/structure`, {});
}

/** LLM summary of a page range (or the whole paper when range omitted). */
export function fetchPdfSummary(
  fileId: string,
  opts: { startPage?: number; endPage?: number; sectionTitle?: string; targetLang?: string } = {},
): Promise<PdfSummaryResponse> {
  return apiClient.post<PdfSummaryResponse>(`/pdf/${fileId}/summary`, {
    start_page: opts.startPage,
    end_page: opts.endPage,
    section_title: opts.sectionTitle,
    target_lang: opts.targetLang,
    ...getPdfModelSelection(),
  });
}

/** References / citation extraction. */
export function fetchPdfCitations(fileId: string): Promise<PdfCitationsResponse> {
  return apiClient.post<PdfCitationsResponse>(`/pdf/${fileId}/citations`, {});
}

/** LLM-assisted extraction of every equation as renderable LaTeX. */
export function fetchPdfFormulas(fileId: string): Promise<PdfFormulasResponse> {
  return apiClient.post<PdfFormulasResponse>(`/pdf/${fileId}/formulas`, {
    ...getPdfModelSelection(),
  });
}

/** Translate free text. */
export function translateText(
  text: string,
  targetLang: string,
): Promise<PdfTranslateResponse> {
  return apiClient.post<PdfTranslateResponse>(`/pdf/translate`, {
    text,
    target_lang: targetLang,
    ...getPdfModelSelection(),
  });
}

/** Translate a page region (bbox in PDF point space) — extracts text + OCR fallback. */
export function translateRegion(
  fileId: string,
  page: number,
  bbox: { x0: number; y0: number; x1: number; y1: number },
  targetLang: string,
): Promise<PdfTranslateResponse> {
  return apiClient.post<PdfTranslateResponse>(`/pdf/translate`, {
    file_id: fileId,
    page,
    bbox: [bbox.x0, bbox.y0, bbox.x1, bbox.y1],
    target_lang: targetLang,
    ...getPdfModelSelection(),
  });
}
