export { PdfReader } from './PdfReader';
export { ResearchPanel } from './ResearchPanel';
export { usePdfResearchStore } from './store/pdfResearchStore';
export type { PdfReaderTarget, PdfReaderMode } from './types';

/** True for PDFs, used to decide whether to surface the reader action. */
export function isPdfTarget(mimeType?: string | null, fileName?: string): boolean {
  if (mimeType && mimeType.toLowerCase() === 'application/pdf') return true;
  return Boolean(fileName && /\.pdf$/i.test(fileName));
}
