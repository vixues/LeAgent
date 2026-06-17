/** Shared types for the PDF Pro Reader + Research Paper Mode. */

export type PdfReaderMode = 'reader' | 'research';

export interface PdfReaderTarget {
  fileId: string;
  fileName: string;
  mimeType?: string | null;
  sizeBytes?: number;
}

/** A normalized rectangle in PDF page space (origin top-left, CSS px at scale 1). */
export interface PageRect {
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface OutlineNode {
  title: string;
  page: number | null;
  level: number;
}

export interface PaperSection {
  id: string;
  title: string;
  page: number;
  level: number;
}

export interface PaperFigure {
  id: string;
  label: string;
  page: number;
  kind: 'figure' | 'table';
  /** Caption (and, for figures, image) bbox in PDF points: [x0, y0, x1, y1]. */
  bbox?: number[];
}

export interface PaperFormula {
  id: string;
  latex: string;
  page: number | null;
  label: string;
  description: string;
  /** True when captured by the LLM-free heuristic fallback (may be imperfect). */
  approx?: boolean;
}

export interface PaperCitation {
  id: string;
  marker: string;
  text: string;
  doi?: string | null;
  url?: string | null;
}

export interface PdfStructureResponse {
  page_count: number;
  title: string | null;
  outline: OutlineNode[];
  sections: PaperSection[];
  figures: PaperFigure[];
}

export interface PdfSummaryResponse {
  summary: string;
  section_title: string | null;
}

export interface PdfCitationsResponse {
  citations: PaperCitation[];
}

export interface PdfFormulasResponse {
  formulas: PaperFormula[];
  /** "ai" when LLM-extracted, "heuristic" when the offline fallback was used. */
  source?: 'ai' | 'heuristic';
}

export interface PdfTranslateResponse {
  source_text: string;
  translated_text: string;
  target_lang: string;
}
