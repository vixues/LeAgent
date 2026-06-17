import { create } from 'zustand';
import type { PdfReaderTarget } from '../types';

/** A highlight region in PDF point space (origin top-left, scale 1). */
export interface HighlightRect {
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Coordinates the chat-page Research Paper experience across two sibling panels:
 * the reader (PDF pages + toolbar, rendered in the artifact panel) and the
 * standalone `ResearchPanel` (the structured `PaperSidebar`). They live in
 * different React subtrees, so navigation requests flow through this store.
 */
interface PdfResearchState {
  /** Whether Research Paper mode is active (sidebar panel + reader shown). */
  active: boolean;
  /** The paper currently under research. */
  target: PdfReaderTarget | null;
  /** Latest page the sidebar asked the reader to scroll to. */
  pageRequest: number | null;
  /** Bumped on every request so the reader re-runs even for the same page. */
  pageNonce: number;
  /** Region to highlight on the page (figures/tables/area selection). */
  highlight: HighlightRect | null;
  start: (target: PdfReaderTarget) => void;
  stop: () => void;
  requestPage: (page: number) => void;
  /** Highlight a region and scroll its page into view. */
  focusRegion: (rect: HighlightRect) => void;
  clearHighlight: () => void;
}

export const usePdfResearchStore = create<PdfResearchState>((set) => ({
  active: false,
  target: null,
  pageRequest: null,
  pageNonce: 0,
  highlight: null,
  start: (target) =>
    set({ active: true, target, pageRequest: null, highlight: null }),
  stop: () =>
    set({ active: false, target: null, pageRequest: null, highlight: null }),
  requestPage: (page) =>
    set((s) => ({ pageRequest: page, pageNonce: s.pageNonce + 1 })),
  focusRegion: (rect) =>
    set((s) => ({
      highlight: rect,
      pageRequest: rect.page,
      pageNonce: s.pageNonce + 1,
    })),
  clearHighlight: () => set({ highlight: null }),
}));
