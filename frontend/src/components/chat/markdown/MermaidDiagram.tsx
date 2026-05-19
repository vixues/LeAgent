import {
  useEffect,
  useRef,
  useState,
  useId,
  useSyncExternalStore,
  memo,
  useCallback,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Download, Code2, Pencil, Maximize2, Check, X, RotateCcw, Plus, Minus } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogClose,
} from '@/components/ui/Dialog';

/* ── ZoomPanContainer ── */

const MIN_SCALE = 0.25;
const MAX_SCALE = 5;
const ZOOM_STEP = 0.15;

interface ZoomPanState {
  scale: number;
  x: number;
  y: number;
}

const zoomBtnClass = cn(
  'flex items-center justify-center w-7 h-7 rounded-md',
  'text-muted-foreground hover:text-foreground hover:bg-surface-sunken/80',
  'transition-colors disabled:opacity-30 disabled:pointer-events-none',
);

function ZoomPanContainer({
  svgHtml,
  className,
  minHeight,
}: {
  svgHtml: string;
  className?: string;
  minHeight?: string;
}) {
  const { t } = useTranslation();
  const [state, setState] = useState<ZoomPanState>({ scale: 1, x: 0, y: 0 });
  const dragging = useRef(false);
  const lastPos = useRef({ x: 0, y: 0 });

  const zoomIn = useCallback(() => {
    setState((prev) => ({
      ...prev,
      scale: Math.min(MAX_SCALE, prev.scale + ZOOM_STEP),
    }));
  }, []);

  const zoomOut = useCallback(() => {
    setState((prev) => ({
      ...prev,
      scale: Math.max(MIN_SCALE, prev.scale - ZOOM_STEP),
    }));
  }, []);

  const handlePointerDown = useCallback((e: ReactPointerEvent) => {
    if (e.button !== 0) return;
    dragging.current = true;
    lastPos.current = { x: e.clientX, y: e.clientY };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, []);

  const handlePointerMove = useCallback((e: ReactPointerEvent) => {
    if (!dragging.current) return;
    const dx = e.clientX - lastPos.current.x;
    const dy = e.clientY - lastPos.current.y;
    lastPos.current = { x: e.clientX, y: e.clientY };
    setState((prev) => ({ ...prev, x: prev.x + dx, y: prev.y + dy }));
  }, []);

  const handlePointerUp = useCallback(() => {
    dragging.current = false;
  }, []);

  const handleReset = useCallback(() => {
    setState({ scale: 1, x: 0, y: 0 });
  }, []);

  const pct = Math.round(state.scale * 100);
  const isDefault = state.scale === 1 && state.x === 0 && state.y === 0;

  return (
    <div className={cn('relative', className)} style={minHeight ? { minHeight } : undefined}>
      <div
        className="w-full h-full overflow-hidden cursor-grab active:cursor-grabbing flex items-center justify-center"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        <div
          className="[&_svg]:max-w-none"
          style={{
            transform: `translate(${state.x}px, ${state.y}px) scale(${state.scale})`,
            willChange: 'transform',
          }}
          dangerouslySetInnerHTML={{ __html: svgHtml }}
        />
      </div>

      {/* Zoom controls */}
      <div className={cn(
        'absolute bottom-2 right-2 z-10 flex items-center gap-0.5 px-1 py-0.5 rounded-lg',
        'bg-surface/80 backdrop-blur-sm border border-border-subtle',
      )}>
        <button
          type="button"
          onClick={zoomOut}
          disabled={state.scale <= MIN_SCALE}
          className={zoomBtnClass}
          aria-label={t('chat.mermaid.zoomOutAria')}
          title={t('chat.mermaid.zoomOutTitle')}
        >
          <Minus className="w-3.5 h-3.5" />
        </button>

        <span className="min-w-[3ch] text-center text-[10px] tabular-nums text-muted-foreground select-none">
          {pct}%
        </span>

        <button
          type="button"
          onClick={zoomIn}
          disabled={state.scale >= MAX_SCALE}
          className={zoomBtnClass}
          aria-label={t('chat.mermaid.zoomInAria')}
          title={t('chat.mermaid.zoomInTitle')}
        >
          <Plus className="w-3.5 h-3.5" />
        </button>

        <button
          type="button"
          onClick={handleReset}
          disabled={isDefault}
          className={zoomBtnClass}
          aria-label={t('chat.mermaid.resetZoomAria')}
          title={t('chat.mermaid.resetZoomTitle')}
        >
          <RotateCcw className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

/* ── MermaidDiagram ── */

interface MermaidDiagramProps {
  source: string;
  className?: string;
}

const svgCache = new Map<string, string>();

function cacheKey(source: string, theme: string): string {
  return `${source}\0${theme}`;
}

function hashCode(s: string): string {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return 'mmd' + Math.abs(h).toString(36);
}

function useColorMode(): 'light' | 'dark' {
  return useSyncExternalStore(
    (cb) => {
      const el = document.documentElement;
      const obs = new MutationObserver(cb);
      obs.observe(el, { attributes: true, attributeFilter: ['class'] });
      return () => obs.disconnect();
    },
    () => (document.documentElement.classList.contains('dark') ? 'dark' : 'light'),
    () => 'light',
  );
}

const DEBOUNCE_MS = 300;

async function downloadSvgAsPng(svgHtml: string, filename: string) {
  const wrapper = document.createElement('div');
  wrapper.innerHTML = svgHtml;
  const svgEl = wrapper.querySelector('svg');
  if (!svgEl) return;

  const bbox = svgEl.getBBox?.();
  const width = bbox?.width || svgEl.clientWidth || 800;
  const height = bbox?.height || svgEl.clientHeight || 600;
  const scale = 2;

  svgEl.setAttribute('width', String(width));
  svgEl.setAttribute('height', String(height));

  const serializer = new XMLSerializer();
  const svgString = serializer.serializeToString(svgEl);
  const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(svgBlob);

  const img = new Image();
  img.crossOrigin = 'anonymous';

  await new Promise<void>((resolve, reject) => {
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = width * scale;
      canvas.height = height * scale;
      const ctx = canvas.getContext('2d')!;
      ctx.scale(scale, scale);
      ctx.drawImage(img, 0, 0, width, height);

      canvas.toBlob((blob) => {
        if (!blob) { reject(new Error('Canvas toBlob failed')); return; }
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        a.click();
        URL.revokeObjectURL(a.href);
        resolve();
      }, 'image/png');
    };
    img.onerror = reject;
    img.src = url;
  });

  URL.revokeObjectURL(url);
}

export const MermaidDiagram = memo(function MermaidDiagram({
  source,
  className,
}: MermaidDiagramProps) {
  const { t } = useTranslation();
  const colorMode = useColorMode();
  const key = cacheKey(source, colorMode);

  const [svg, setSvg] = useState<string | null>(() => svgCache.get(key) ?? null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [showCode, setShowCode] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editSource, setEditSource] = useState(source);
  const [editSvg, setEditSvg] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [codeCopied, setCodeCopied] = useState(false);
  const uniqueId = useId().replace(/:/g, '_');

  const sourceRef = useRef(source);
  sourceRef.current = source;

  useEffect(() => {
    if (svgCache.has(key)) {
      setSvg(svgCache.get(key)!);
      setError(null);
      return;
    }

    let cancelled = false;

    const timer = window.setTimeout(async () => {
      if (cancelled) return;
      if (sourceRef.current !== source) return;

      try {
        const [mermaidMod, dpMod] = await Promise.all([
          import('mermaid'),
          import('dompurify'),
        ]);
        const mermaid = mermaidMod.default;
        const DOMPurify = dpMod.default;

        mermaid.initialize({
          startOnLoad: false,
          theme: colorMode === 'dark' ? 'dark' : 'default',
          securityLevel: 'strict',
          fontFamily: 'Inter, system-ui, sans-serif',
        });

        const { svg: rendered } = await mermaid.render(
          `mermaid_${uniqueId}_${hashCode(source)}`,
          source,
        );

        const sanitized = DOMPurify.sanitize(rendered, {
          USE_PROFILES: { svg: true, svgFilters: true },
          ADD_TAGS: ['foreignObject'],
        });

        if (!cancelled) {
          svgCache.set(key, sanitized);
          setSvg(sanitized);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError((err as Error).message || t('chat.mermaid.renderErrorFallback'));
          setSvg(null);
        }
      }
    }, DEBOUNCE_MS);

    setSvg(null);
    setError(null);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [key, source, colorMode, uniqueId, t]);

  const handleExpand = useCallback(() => setExpanded(true), []);
  const handleCollapse = useCallback(() => setExpanded(false), []);

  const handleDownload = useCallback(() => {
    if (!svg) return;
    void downloadSvgAsPng(svg, 'mermaid-diagram.png');
  }, [svg]);

  const handleToggleCode = useCallback(() => {
    setShowCode((v) => !v);
    setEditing(false);
  }, []);

  const handleCopyCode = useCallback(async () => {
    await navigator.clipboard.writeText(source);
    setCodeCopied(true);
    setTimeout(() => setCodeCopied(false), 2000);
  }, [source]);

  const [editRendering, setEditRendering] = useState(false);

  const handleStartEdit = useCallback(() => {
    setEditSource(source);
    setEditSvg(null);
    setEditError(null);
    setEditing(true);
    setShowCode(false);
  }, [source]);

  const handleCancelEdit = useCallback(() => {
    setEditing(false);
    setEditSource(source);
    setEditSvg(null);
    setEditError(null);
  }, [source]);

  const editSourceRef = useRef(editSource);
  editSourceRef.current = editSource;

  useEffect(() => {
    if (!editing || !editSource.trim()) return;

    let cancelled = false;
    setEditRendering(true);

    const timer = window.setTimeout(async () => {
      if (cancelled) return;
      if (editSourceRef.current !== editSource) return;

      try {
        const [mermaidMod, dpMod] = await Promise.all([
          import('mermaid'),
          import('dompurify'),
        ]);
        const mermaid = mermaidMod.default;
        const DOMPurify = dpMod.default;

        mermaid.initialize({
          startOnLoad: false,
          theme: colorMode === 'dark' ? 'dark' : 'default',
          securityLevel: 'strict',
          fontFamily: 'Inter, system-ui, sans-serif',
        });

        const { svg: rendered } = await mermaid.render(
          `mermaid_edit_${uniqueId}_${hashCode(editSource)}`,
          editSource,
        );

        const sanitized = DOMPurify.sanitize(rendered, {
          USE_PROFILES: { svg: true, svgFilters: true },
          ADD_TAGS: ['foreignObject'],
        });

        if (!cancelled) {
          setEditSvg(sanitized);
          setEditError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setEditError((err as Error).message || t('chat.mermaid.renderErrorFallback'));
          setEditSvg(null);
        }
      } finally {
        if (!cancelled) setEditRendering(false);
      }
    }, 500);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [editing, editSource, colorMode, uniqueId, t]);

  /* ── Loading ── */
  if (!svg && !error) {
    return (
      <div
        className={cn(
          'flex items-center justify-center h-32 rounded-xl border border-border-subtle bg-surface-sunken/40',
          className,
        )}
      >
        <div className="w-5 h-5 border-2 border-primary-400 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  /* ── Render error ── */
  if (error) {
    return (
      <div
        className={cn(
          'rounded-xl border border-red-200 dark:border-red-800 bg-red-50/50 dark:bg-red-900/10 p-4 text-sm text-red-600 dark:text-red-400',
          className,
        )}
      >
        <p className="font-medium mb-1">{t('chat.mermaid.renderError')}</p>
        <pre className="text-xs whitespace-pre-wrap font-mono">{error}</pre>
      </div>
    );
  }

  const toolbarBtnClass = cn(
    'flex items-center justify-center w-7 h-7 rounded-md',
    'text-muted-foreground hover:text-foreground hover:bg-surface-sunken/80',
    'transition-colors',
  );

  return (
    <>
      <div
        className={cn(
          'group/mermaid relative rounded-xl border border-border-subtle bg-surface-sunken/30 overflow-hidden my-3',
          className,
        )}
      >
        {/* ── Toolbar ── */}
        <div className={cn(
          'flex items-center gap-0.5 px-2 py-1.5 border-b border-border-subtle/60',
          'opacity-0 group-hover/mermaid:opacity-100 focus-within:opacity-100 transition-opacity',
          'bg-surface-sunken/50',
        )}>
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mr-auto select-none">
            Mermaid
          </span>

          <button
            type="button"
            onClick={handleToggleCode}
            className={cn(toolbarBtnClass, showCode && 'text-primary-600 dark:text-primary-400 bg-primary-500/10')}
            aria-label={t('chat.mermaid.codeAria')}
            title={t('chat.mermaid.codeTitle')}
          >
            <Code2 className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={handleStartEdit}
            className={toolbarBtnClass}
            aria-label={t('chat.mermaid.editAria')}
            title={t('chat.mermaid.editTitle')}
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={handleDownload}
            className={toolbarBtnClass}
            aria-label={t('chat.mermaid.downloadAria')}
            title={t('chat.mermaid.downloadTitle')}
          >
            <Download className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={handleExpand}
            className={toolbarBtnClass}
            aria-label={t('chat.mermaid.expandAria')}
            title={t('chat.mermaid.expandTitle')}
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* ── Code view ── */}
        {showCode && (
          <div className="border-b border-border-subtle/60 bg-[hsl(var(--surface-sunken))] relative">
            <pre className="p-3 text-xs font-mono whitespace-pre-wrap break-words text-foreground/90 max-h-64 overflow-auto">
              {source}
            </pre>
            <button
              type="button"
              onClick={handleCopyCode}
              className={cn(
                'absolute top-2 right-2 flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium',
                'bg-surface/80 border border-border-subtle text-muted-foreground hover:text-foreground transition-colors',
              )}
              title={t('common.copy')}
            >
              {codeCopied ? <Check className="w-3 h-3 text-emerald-500" /> : <Code2 className="w-3 h-3" />}
              {codeCopied ? t('chat.copied') : t('common.copy')}
            </button>
          </div>
        )}

        {/* ── Diagram ── */}
        <ZoomPanContainer svgHtml={svg!} className="p-4" minHeight="6rem" />
      </div>

      {/* ── Expand dialog ── */}
      <Dialog open={expanded} onOpenChange={handleCollapse}>
        <DialogContent
          className="max-w-[92vw] max-h-[92vh] w-[85vw] h-[85vh]"
          size="xl"
        >
          <DialogClose className="z-20" />
          <ZoomPanContainer svgHtml={svg!} className="w-full h-full" />
        </DialogContent>
      </Dialog>

      {/* ── Edit dialog ── */}
      <Dialog open={editing} onOpenChange={(open) => { if (!open) handleCancelEdit(); }}>
        <DialogContent
          className="max-w-[90vw] w-full max-h-[90vh] h-[80vh]"
          size="xl"
        >
          <div className="flex flex-col h-full">
            <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-border shrink-0">
              <Pencil className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm font-semibold text-foreground">{t('chat.mermaid.editDialogTitle')}</span>
              <button
                type="button"
                onClick={handleCancelEdit}
                className={cn(
                  'ml-auto p-1.5 rounded-lg',
                  'text-muted-foreground-tertiary hover:text-foreground',
                  'hover:bg-surface-sunken dark:hover:bg-surface-elevated transition-colors',
                )}
                aria-label={t('common.close')}
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex flex-1 min-h-0 divide-x divide-border">
              {/* Editor pane */}
              <div className="flex-1 min-w-0 flex flex-col">
                <div className="px-4 py-2 border-b border-border-subtle/60 shrink-0">
                  <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                    Mermaid
                  </span>
                </div>
                <textarea
                  value={editSource}
                  onChange={(e) => setEditSource(e.target.value)}
                  spellCheck={false}
                  className={cn(
                    'flex-1 min-h-0 w-full resize-none p-5',
                    'font-mono text-sm leading-relaxed',
                    'bg-transparent text-foreground',
                    'focus:outline-none',
                    'placeholder:text-muted-foreground-tertiary',
                  )}
                  placeholder={t('chat.mermaid.editPlaceholder')}
                />
              </div>

              {/* Preview pane */}
              <div className="flex-1 min-w-0 flex flex-col bg-surface-sunken/30">
                <div className="px-4 py-2 border-b border-border-subtle/60 shrink-0 flex items-center gap-2">
                  <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                    {t('chat.mermaid.previewLabel')}
                  </span>
                  {editRendering && (
                    <div className="w-3 h-3 border-[1.5px] border-primary-400 border-t-transparent rounded-full animate-spin" />
                  )}
                </div>
                <div className="flex-1 min-h-0 flex items-center justify-center">
                  {editError ? (
                    <div className="text-sm text-red-500 font-mono whitespace-pre-wrap max-w-full p-5">
                      {editError}
                    </div>
                  ) : editSvg ? (
                    <ZoomPanContainer svgHtml={editSvg} className="w-full h-full" />
                  ) : editRendering ? (
                    <div className="w-5 h-5 border-2 border-primary-400 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <p className="text-sm text-muted-foreground-tertiary italic">
                      {t('chat.mermaid.previewHint')}
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
});
