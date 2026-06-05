import { useCallback, useRef, useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { Code2, Sparkles } from 'lucide-react';
import { toPng } from 'html-to-image';
import { genUiTreeKey, useGenUiStore } from '@/stores/genUi';
import { GenUiTreeView } from './GenUiRegistry';
import { CameraCaptureModal } from '@/components/chat/CameraCaptureModal';
import { Modal } from '@/components/ui/Modal';
import { cn } from '@/lib/utils';
import { exportGenUiTreeToPdf } from '@/components/canvas/genUi/useGenUiExportPdf';
import { GenUiInlineToolbar } from '@/components/canvas/genUi/GenUiInlineToolbar';
import {
  deckScreenshotDimensions,
  documentScreenshotDimensions,
} from '@/components/canvas/genUi/genUiExportDimensions';
import {
  expandScrollContainersForCapture,
  flushLayout,
  nextDoubleFrame,
} from '@/components/canvas/genUi/genUiCaptureDom';

/**
 * Renders a streamed generative UI tree in the chat column when the agent
 * uses `emit_ui_tree` (even without a canvas HTML artifact).
 */
export function GenUiInline({
  sessionId,
  messageId,
  className,
}: {
  sessionId: string;
  messageId: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const key = genUiTreeKey(sessionId, messageId);
  const tree = useGenUiStore((s) => s.trees[key]);
  const [expanded, setExpanded] = useState(false);
  const [jsEnabled, setJsEnabled] = useState(false);
  const [screenshotting, setScreenshotting] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [floatingOpen, setFloatingOpen] = useState(false);
  const [pdfExporting, setPdfExporting] = useState(false);
  const treeBodyRef = useRef<HTMLDivElement>(null);
  const floatingBodyRef = useRef<HTMLDivElement>(null);

  const runScreenshot = useCallback(
    async (ref: RefObject<HTMLDivElement | null>) => {
      const el = ref.current;
      if (!el || screenshotting) return;
      const isDeck = tree?.root?.kind === 'SlideDeck';
      setScreenshotting(true);
      const restoreDom = expandScrollContainersForCapture(el);
      try {
        flushLayout(el);
        await nextDoubleFrame();
        let bg = window.getComputedStyle(el).backgroundColor;
        if (!bg || bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent') {
          bg = window.getComputedStyle(document.documentElement).backgroundColor;
        }
        const bgOpt =
          bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent' ? bg : undefined;
        const dims = isDeck ? deckScreenshotDimensions(el) : documentScreenshotDimensions(el);
        const dataUrl = await toPng(el, {
          pixelRatio: 2,
          cacheBust: true,
          backgroundColor: bgOpt,
          width: dims.width,
          height: dims.height,
        });
        const a = document.createElement('a');
        a.href = dataUrl;
        a.download = `genui-${messageId.slice(0, 8)}.png`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } catch {
        // Best-effort: CORS images or unsupported nodes can fail capture
      } finally {
        restoreDom();
        setScreenshotting(false);
      }
    },
    [messageId, screenshotting, tree?.root?.kind],
  );

  const handleExportPdf = useCallback(async () => {
    if (!tree || pdfExporting) return;
    setPdfExporting(true);
    try {
      const rootKind = tree.root?.kind;
      await exportGenUiTreeToPdf({
        sessionId,
        messageId,
        tree,
        mode: rootKind === 'SlideDeck' ? 'deck' : 'document',
        pageSize: rootKind === 'SlideDeck' ? 'Slide16x9' : 'A4',
        orientation: rootKind === 'SlideDeck' ? 'landscape' : 'portrait',
      });
    } catch {
      /* best-effort */
    } finally {
      setPdfExporting(false);
    }
  }, [tree, sessionId, messageId, pdfExporting]);

  if (!tree) return null;

  const isDeck = tree.root?.kind === 'SlideDeck';
  const maxH = isDeck
    ? expanded
      ? 'max-h-[min(90vh,900px)]'
      : 'max-h-[min(70vh,640px)]'
    : expanded
      ? 'max-h-[600px]'
      : 'max-h-96';

  return (
    <div
      className={cn(
        'mt-3 rounded-xl border border-border bg-surface-elevated/50 overflow-hidden transition-all duration-300',
        className,
      )}
    >
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-surface-sunken/50">
        <div className="flex items-center gap-1.5">
          <Sparkles className="w-3 h-3 text-primary-500" />
          <span className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">
            Generative UI
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setJsEnabled((v) => !v)}
            className={cn(
              'p-0.5 rounded transition-colors',
              jsEnabled
                ? 'text-foreground bg-surface-sunken'
                : 'text-muted-foreground hover:text-foreground hover:bg-surface-sunken',
            )}
            aria-label={jsEnabled ? t('chat.canvas.jsOn') : t('chat.canvas.jsOff')}
            title={jsEnabled ? t('chat.canvas.jsOn') : t('chat.canvas.jsOff')}
            aria-pressed={jsEnabled}
          >
            <Code2 className="w-3.5 h-3.5" aria-hidden />
          </button>
          <GenUiInlineToolbar
            showEnlarge
            onEnlarge={() => setFloatingOpen(true)}
            onExportPdf={handleExportPdf}
            pdfExporting={pdfExporting}
            onScreenshot={() => void runScreenshot(treeBodyRef)}
            screenshotting={screenshotting}
            onCameraOpen={() => setCameraOpen(true)}
            expanded={expanded}
            onToggleExpanded={() => setExpanded((e) => !e)}
          />
        </div>
      </div>
      <div className={cn('overflow-auto transition-all duration-300', maxH)}>
        <GenUiTreeView
          tree={tree}
          contentRef={treeBodyRef}
          sessionId={sessionId}
          messageId={messageId}
          jsEnabled={jsEnabled}
        />
      </div>
      <CameraCaptureModal open={cameraOpen} onOpenChange={setCameraOpen} />

      <Modal
        isOpen={floatingOpen}
        onClose={() => setFloatingOpen(false)}
        size="2xl"
        className={cn(
          'flex h-[min(90vh,calc(100dvh-2rem))] min-h-0 max-h-[90vh] w-full max-w-[min(100%,80rem)] flex-col gap-0 overflow-hidden p-0',
        )}
      >
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-2 text-base font-semibold text-foreground">
            <Sparkles className="h-4 w-4 shrink-0 text-primary-500" aria-hidden />
            Generative UI
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => setJsEnabled((v) => !v)}
              className={cn(
                'p-0.5 rounded transition-colors',
                jsEnabled
                  ? 'text-foreground bg-surface-sunken'
                  : 'text-muted-foreground hover:text-foreground hover:bg-surface-sunken',
              )}
              aria-label={jsEnabled ? t('chat.canvas.jsOn') : t('chat.canvas.jsOff')}
              title={jsEnabled ? t('chat.canvas.jsOn') : t('chat.canvas.jsOff')}
              aria-pressed={jsEnabled}
            >
              <Code2 className="w-3.5 h-3.5" aria-hidden />
            </button>
            <GenUiInlineToolbar
              showEnlarge={false}
              showExpandToggle={false}
              onExportPdf={handleExportPdf}
              pdfExporting={pdfExporting}
              onScreenshot={() => void runScreenshot(floatingBodyRef)}
              screenshotting={screenshotting}
              onCameraOpen={() => setCameraOpen(true)}
            />
            <button
              type="button"
              onClick={() => setFloatingOpen(false)}
              className="shrink-0 rounded-lg p-1.5 text-muted-foreground-tertiary transition-colors hover:bg-surface-sunken hover:text-foreground dark:hover:bg-surface-elevated"
              aria-label="Close"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-background">
          <GenUiTreeView
            tree={tree}
            contentRef={floatingBodyRef}
            sessionId={sessionId}
            messageId={messageId}
            jsEnabled={jsEnabled}
          />
        </div>
      </Modal>
    </div>
  );
}
