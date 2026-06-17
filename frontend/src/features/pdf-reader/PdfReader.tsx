import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Languages, Loader2, MessageSquarePlus, Sparkles, X } from 'lucide-react';
import { useToast } from '@/components/ui/Toaster';
import { downloadAuthenticatedFile } from '@/lib/downloadAuthenticatedFile';
import { usePdfDocument } from './usePdfDocument';
import { usePdfResearchStore } from './store/pdfResearchStore';
import { PdfToolbar } from './PdfToolbar';
import { PdfPage, type AreaSelection } from './PdfPage';
import { PdfThumbnails } from './PdfThumbnails';
import { PdfSearchBar } from './PdfSearchBar';
import { PaperSidebar } from './PaperSidebar';
import { TextSelectionMenu } from './selection/TextSelectionMenu';
import { PdfContextMenu } from './selection/PdfContextMenu';
import { translateRegion, translateText } from './api/pdfReaderApi';
import {
  appendPrompt,
  attachImage,
  canvasRegionToFile,
  canvasToFile,
  copyImage,
  copyText,
  ensurePaperReferenced,
  focusComposer,
  insertExplain,
  insertQuote,
} from './readerComposerBridge';
import type {
  PaperFigure,
  PaperFormula,
  PdfReaderMode,
  PdfReaderTarget,
  PdfTranslateResponse,
} from './types';

interface PdfReaderProps {
  target: PdfReaderTarget;
  /** Called when the user closes the reader (returns to the plain preview). */
  onClose: () => void;
  initialMode?: PdfReaderMode;
  /**
   * When true the structured `PaperSidebar` is rendered in a separate chat-page
   * panel (`ResearchPanel`) instead of inline. The reader then listens to the
   * research store for page-jump requests coming from that panel.
   */
  externalSidebar?: boolean;
}

const MIN_SCALE = 0.4;
const MAX_SCALE = 3;
const RENDER_WINDOW = 3;

/**
 * Embeddable professional PDF reader. Renders inline (e.g. inside the chat
 * artifact panel) — interactions feed the existing chat composer via the
 * `readerComposerBridge`, so there is no separate chat dock here.
 */
export function PdfReader({
  target,
  onClose,
  initialMode = 'reader',
  externalSidebar = false,
}: PdfReaderProps) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const { doc, numPages, loading, error } = usePdfDocument(target.fileId);

  const [mode, setMode] = useState<PdfReaderMode>(initialMode);
  const [page, setPage] = useState(1);
  const [scale, setScale] = useState(1.1);
  const [rotation, setRotation] = useState(0);
  const [areaMode, setAreaMode] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [thumbnailsOpen, setThumbnailsOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(initialMode === 'research');
  const [areaSel, setAreaSel] = useState<AreaSelection | null>(null);
  const [translation, setTranslation] = useState<PdfTranslateResponse | null>(null);
  const [translating, setTranslating] = useState(false);
  const [summaryCard, setSummaryCard] = useState<{ title: string; body: string } | null>(
    null,
  );

  const pagesRef = useRef<HTMLDivElement>(null);
  const baseWidthRef = useRef<number>(612);
  const baseHeightRef = useRef<number>(792);
  const targetLang = i18n.language || 'en';

  // When the structured sidebar lives in its own panel, it drives navigation
  // through the research store rather than a direct callback.
  const researchPageNonce = usePdfResearchStore((s) => s.pageNonce);
  const researchPageRequest = usePdfResearchStore((s) => s.pageRequest);
  const highlight = usePdfResearchStore((s) => s.highlight);
  const clearHighlight = usePdfResearchStore((s) => s.clearHighlight);
  const focusRegion = usePdfResearchStore((s) => s.focusRegion);

  useEffect(() => {
    setSidebarOpen(mode === 'research');
  }, [mode]);

  useEffect(() => {
    if (!doc) return;
    let cancelled = false;
    void doc.getPage(1).then((p) => {
      if (cancelled) return;
      const vp = p.getViewport({ scale: 1 });
      baseWidthRef.current = vp.width;
      baseHeightRef.current = vp.height;
    });
    return () => {
      cancelled = true;
    };
  }, [doc]);

  const jumpToPage = useCallback(
    (p: number) => {
      const clamped = Math.max(1, Math.min(numPages || 1, p));
      setPage(clamped);
      const el = pagesRef.current?.querySelector(`[data-page="${clamped}"]`);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
    [numPages],
  );

  useEffect(() => {
    if (!externalSidebar) return;
    if (researchPageRequest == null) return;
    jumpToPage(researchPageRequest);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [researchPageNonce]);

  // A figure/table highlight flashes to locate the region, then fades.
  useEffect(() => {
    if (!highlight) return;
    const id = window.setTimeout(() => clearHighlight(), 4500);
    return () => window.clearTimeout(id);
  }, [highlight, clearHighlight]);

  const fitWidth = useCallback(() => {
    const container = pagesRef.current;
    if (!container) return;
    const avail = container.clientWidth - 40;
    if (avail > 0) {
      setScale(
        Math.max(MIN_SCALE, Math.min(MAX_SCALE, avail / baseWidthRef.current)),
      );
    }
  }, []);

  const handleDownload = useCallback(() => {
    void downloadAuthenticatedFile(target.fileId, target.fileName);
  }, [target.fileId, target.fileName]);

  const doTranslate = useCallback(
    async (fn: () => Promise<PdfTranslateResponse>) => {
      setTranslating(true);
      setTranslation(null);
      try {
        setTranslation(await fn());
      } catch {
        toast({
          title: t('pdfReader.translate.failed', { defaultValue: 'Translation failed.' }),
          variant: 'error',
        });
      } finally {
        setTranslating(false);
      }
    },
    [t, toast],
  );

  const onTranslateText = useCallback(
    (text: string) => void doTranslate(() => translateText(text, targetLang)),
    [doTranslate, targetLang],
  );

  const onInsertText = useCallback(
    (text: string) => {
      ensurePaperReferenced(target);
      insertQuote(text, page);
      toast({
        title: t('pdfReader.toast.inserted', { defaultValue: 'Added to chat input' }),
        variant: 'success',
      });
    },
    [page, t, target, toast],
  );

  const onAskText = useCallback(
    (text: string) => {
      ensurePaperReferenced(target);
      insertQuote(text, page);
      focusComposer();
    },
    [page, target],
  );

  const onCopyText = useCallback(
    (text: string) => {
      void copyText(text).then((ok) =>
        toast({
          title: ok
            ? t('pdfReader.toast.copied', { defaultValue: 'Copied to clipboard' })
            : t('pdfReader.toast.copyFailed', { defaultValue: 'Copy failed' }),
          variant: ok ? 'success' : 'error',
        }),
      );
    },
    [t, toast],
  );

  const onExplainText = useCallback(
    (text: string) => {
      ensurePaperReferenced(target);
      insertExplain(
        t('pdfReader.selection.explainPrompt', {
          defaultValue: 'Explain the following passage from this paper in clear terms:',
        }),
        text,
        page,
      );
      focusComposer();
    },
    [page, t, target],
  );

  const onAreaSelected = useCallback((sel: AreaSelection) => setAreaSel(sel), []);

  const cropArea = useCallback(
    async (sel: AreaSelection): Promise<File | null> => {
      const outputScale = window.devicePixelRatio || 1;
      return canvasRegionToFile(
        sel.canvas,
        {
          x: sel.cssRect.x * outputScale,
          y: sel.cssRect.y * outputScale,
          width: sel.cssRect.width * outputScale,
          height: sel.cssRect.height * outputScale,
        },
        `${target.fileName}-p${sel.page}-region.png`,
      );
    },
    [target.fileName],
  );

  const onAskArea = useCallback(
    async (sel: AreaSelection) => {
      const file = await cropArea(sel);
      if (!file) return;
      attachImage(file);
      ensurePaperReferenced(target);
      setAreaSel(null);
      setAreaMode(false);
      toast({
        title: t('pdfReader.toast.regionAttached', {
          defaultValue: 'Region attached to chat. Add your question and send.',
        }),
        variant: 'success',
      });
    },
    [cropArea, t, target, toast],
  );

  const onTranslateArea = useCallback(
    (sel: AreaSelection) => {
      setAreaSel(null);
      void doTranslate(() =>
        translateRegion(target.fileId, sel.page, sel.pdfRect, targetLang),
      );
    },
    [doTranslate, target.fileId, targetLang],
  );

  const onCopyArea = useCallback(
    async (sel: AreaSelection) => {
      const file = await cropArea(sel);
      if (!file) return;
      const ok = await copyImage(file);
      setAreaSel(null);
      setAreaMode(false);
      toast({
        title: ok
          ? t('pdfReader.toast.copied', { defaultValue: 'Copied to clipboard' })
          : t('pdfReader.toast.copyFailed', { defaultValue: 'Copy failed' }),
        variant: ok ? 'success' : 'error',
      });
    },
    [cropArea, t, toast],
  );

  const onExplainArea = useCallback(
    async (sel: AreaSelection) => {
      const file = await cropArea(sel);
      if (!file) return;
      attachImage(file);
      ensurePaperReferenced(target);
      insertExplain(
        t('pdfReader.selection.explainRegionPrompt', {
          defaultValue:
            'Explain the attached region from page {{page}} of this paper.',
          page: sel.page,
        }),
        '',
      );
      setAreaSel(null);
      setAreaMode(false);
      focusComposer();
    },
    [cropArea, t, target],
  );

  const onScreenshot = useCallback(async () => {
    const canvas = pagesRef.current?.querySelector<HTMLCanvasElement>(
      `[data-page="${page}"] canvas`,
    );
    if (!canvas) return;
    const file = await canvasToFile(canvas, `${target.fileName}-p${page}.png`);
    if (!file) return;
    attachImage(file);
    ensurePaperReferenced(target);
    toast({
      title: t('pdfReader.toast.screenshotAttached', {
        defaultValue: 'Page screenshot attached to chat.',
      }),
      variant: 'success',
    });
  }, [page, t, target, toast]);

  const onAskAboutFigure = useCallback(
    (figure: PaperFigure) => {
      jumpToPage(figure.page);
      ensurePaperReferenced(target);
      insertQuote(
        t('pdfReader.figure.askPrompt', {
          defaultValue: 'Explain {{label}} (page {{page}}) in this paper.',
          label: figure.label,
          page: figure.page,
        }),
      );
    },
    [jumpToPage, t, target],
  );

  const onFocusFigure = useCallback(
    (figure: PaperFigure) => {
      if (figure.bbox && figure.bbox.length === 4) {
        const [x0 = 0, y0 = 0, x1 = 0, y1 = 0] = figure.bbox;
        focusRegion({ page: figure.page, x: x0, y: y0, width: x1 - x0, height: y1 - y0 });
      }
      jumpToPage(figure.page);
    },
    [focusRegion, jumpToPage],
  );

  const onAnalyzeFormula = useCallback(
    (formula: PaperFormula) => {
      ensurePaperReferenced(target);
      const pageRef = formula.page ? ` (p.${formula.page})` : '';
      appendPrompt(
        t('pdfReader.sidebar.analyzeFormulaPrompt', {
          defaultValue:
            'Analyze this formula from the paper{{page}} in depth: define every symbol, explain what it computes and why, and note assumptions or limitations.',
          page: pageRef,
        }) + `\n\n$$\n${formula.latex}\n$$`,
      );
      focusComposer();
    },
    [t, target],
  );

  const renderWindow = useMemo(() => {
    const start = Math.max(1, page - RENDER_WINDOW);
    const end = Math.min(numPages || 1, page + RENDER_WINDOW);
    return { start, end };
  }, [page, numPages]);

  const placeholderHeight = useMemo(
    () => (baseHeightRef.current / baseWidthRef.current) * baseWidthRef.current * scale,
    [scale],
  );

  return (
    <div className="relative flex h-full min-h-0 w-full flex-col overflow-hidden rounded-lg border border-border bg-background">
      <PdfToolbar
        fileName={target.fileName}
        page={page}
        numPages={numPages}
        scale={scale}
        mode={mode}
        sidebarOpen={sidebarOpen}
        thumbnailsOpen={thumbnailsOpen}
        areaMode={areaMode}
        searchOpen={searchOpen}
        showSidebarToggle={!externalSidebar}
        showModeToggle={!externalSidebar}
        onPageChange={jumpToPage}
        onZoomIn={() => setScale((s) => Math.min(MAX_SCALE, s + 0.2))}
        onZoomOut={() => setScale((s) => Math.max(MIN_SCALE, s - 0.2))}
        onFitWidth={fitWidth}
        onRotate={() => setRotation((r) => (r + 90) % 360)}
        onToggleSidebar={() => setSidebarOpen((v) => !v)}
        onToggleThumbnails={() => setThumbnailsOpen((v) => !v)}
        onToggleArea={() => setAreaMode((v) => !v)}
        onToggleSearch={() => setSearchOpen((v) => !v)}
        onScreenshot={onScreenshot}
        onToggleMode={() => setMode(mode === 'research' ? 'reader' : 'research')}
        onDownload={handleDownload}
        onClose={onClose}
      />

      <div className="flex min-h-0 flex-1">
        {!externalSidebar && sidebarOpen && mode === 'research' && (
          <div className="flex h-full w-72 flex-shrink-0 flex-col border-r border-border">
            <PaperSidebar
              fileId={target.fileId}
              onJumpToPage={jumpToPage}
              onAskAboutFigure={onAskAboutFigure}
              onFocusFigure={onFocusFigure}
              onAnalyzeFormula={onAnalyzeFormula}
              onShowSummary={(title, body) => setSummaryCard({ title, body })}
            />
          </div>
        )}

        {thumbnailsOpen && doc && (
          <PdfThumbnails
            doc={doc}
            numPages={numPages}
            currentPage={page}
            onSelect={jumpToPage}
          />
        )}

        <div className="relative min-w-0 flex-1 bg-surface-sunken/40">
          {searchOpen && doc && (
            <PdfSearchBar doc={doc} onJump={jumpToPage} onClose={() => setSearchOpen(false)} />
          )}

          <div ref={pagesRef} className="h-full overflow-auto px-4 py-2">
            <TextSelectionMenu
              containerRef={pagesRef}
              onInsert={onInsertText}
              onTranslate={onTranslateText}
              onAsk={onAskText}
              onCopy={onCopyText}
              onExplain={onExplainText}
            />

            <PdfContextMenu
              containerRef={pagesRef}
              onCopy={onCopyText}
              onExplain={onExplainText}
              onQuote={onInsertText}
              onTranslate={onTranslateText}
              onAsk={onAskText}
              onScreenshot={() => void onScreenshot()}
              onToggleArea={() => setAreaMode((v) => !v)}
            />

            {loading && (
              <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                {t('pdfReader.loading', { defaultValue: 'Loading PDF…' })}
              </div>
            )}
            {error && (
              <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted-foreground">
                {t('pdfReader.error', { defaultValue: 'Could not load this PDF.' })}
              </div>
            )}

            {doc &&
              Array.from({ length: numPages }, (_, i) => i + 1).map((p) => {
                const inWindow = p >= renderWindow.start && p <= renderWindow.end;
                return inWindow ? (
                  <PdfPage
                    key={p}
                    doc={doc}
                    pageNumber={p}
                    scale={scale}
                    rotation={rotation}
                    areaMode={areaMode}
                    onAreaSelected={onAreaSelected}
                    onVisible={setPage}
                    highlightRect={
                      highlight && highlight.page === p
                        ? {
                            x: highlight.x,
                            y: highlight.y,
                            width: highlight.width,
                            height: highlight.height,
                          }
                        : areaSel && areaSel.page === p
                          ? {
                              x: areaSel.pdfRect.x0,
                              y: areaSel.pdfRect.y0,
                              width: areaSel.pdfRect.x1 - areaSel.pdfRect.x0,
                              height: areaSel.pdfRect.y1 - areaSel.pdfRect.y0,
                            }
                          : null
                    }
                  />
                ) : (
                  <div
                    key={p}
                    data-page={p}
                    className="mx-auto my-4 flex items-center justify-center bg-white/40 text-xs text-muted-foreground ring-1 ring-border"
                    style={{ width: baseWidthRef.current * scale, height: placeholderHeight }}
                  >
                    {p}
                  </div>
                );
              })}
          </div>

          {areaSel && (
            <div
              className="absolute z-40 flex items-center gap-0.5 rounded-lg border border-border bg-surface p-1 shadow-lg"
              style={{ left: 16, bottom: 16 }}
            >
              <button
                type="button"
                onClick={() => void onExplainArea(areaSel)}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-foreground hover:bg-surface-sunken"
              >
                <Sparkles className="h-3.5 w-3.5" />
                {t('pdfReader.selection.explain', { defaultValue: 'Explain' })}
              </button>
              <button
                type="button"
                onClick={() => void onCopyArea(areaSel)}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-foreground hover:bg-surface-sunken"
              >
                <Copy className="h-3.5 w-3.5" />
                {t('pdfReader.selection.copy', { defaultValue: 'Copy' })}
              </button>
              <button
                type="button"
                onClick={() => onTranslateArea(areaSel)}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-foreground hover:bg-surface-sunken"
              >
                <Languages className="h-3.5 w-3.5" />
                {t('pdfReader.selection.translate', { defaultValue: 'Translate' })}
              </button>
              <button
                type="button"
                onClick={() => void onAskArea(areaSel)}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-foreground hover:bg-surface-sunken"
              >
                <MessageSquarePlus className="h-3.5 w-3.5" />
                {t('pdfReader.selection.ask', { defaultValue: 'Ask' })}
              </button>
              <button
                type="button"
                onClick={() => setAreaSel(null)}
                className="rounded p-1 text-muted-foreground hover:bg-surface-sunken"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {(translating || translation) && (
            <div className="absolute bottom-4 left-1/2 z-40 w-[min(34rem,90%)] -translate-x-1/2 rounded-lg border border-border bg-surface p-3 shadow-xl">
              <div className="mb-1 flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                  <Languages className="h-3.5 w-3.5 text-primary-600" />
                  {t('pdfReader.translate.title', { defaultValue: 'Translation' })}
                </span>
                <button
                  type="button"
                  onClick={() => setTranslation(null)}
                  className="rounded p-1 text-muted-foreground hover:bg-surface-sunken"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
              {translating ? (
                <div className="flex items-center gap-2 py-3 text-xs text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t('pdfReader.translate.working', { defaultValue: 'Translating…' })}
                </div>
              ) : (
                <p className="max-h-48 overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                  {translation?.translated_text}
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {summaryCard && (
        <div
          className="absolute inset-0 z-50 flex items-center justify-center bg-black/40 p-6"
          onClick={() => setSummaryCard(null)}
        >
          <div
            className="max-h-[80%] w-[min(40rem,92%)] overflow-y-auto rounded-xl border border-border bg-surface p-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground">{summaryCard.title}</h3>
              <button
                type="button"
                onClick={() => setSummaryCard(null)}
                className="rounded p-1 text-muted-foreground hover:bg-surface-sunken"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
              {summaryCard.body}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
