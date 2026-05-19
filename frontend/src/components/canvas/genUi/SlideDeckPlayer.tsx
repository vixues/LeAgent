import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  ArrowLeft,
  ArrowRight,
  ChevronsLeft,
  ChevronsRight,
  FileDown,
  Maximize2,
  Minimize2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { GenUiNode, GenUiTreeV1 } from '@/types/genUi';
import type { GenUiRenderContextValue } from '@/components/canvas/genUi/GenUiRenderContext';
import { exportGenUiTreeToPdf } from '@/components/canvas/genUi/useGenUiExportPdf';

const b = (v: unknown): boolean => Boolean(v);
const s = (v: unknown): string => (typeof v === 'string' ? v : v != null ? String(v) : '');

/** Map aspectRatio prop to Tailwind aspect class + CSS ratio string. */
function aspectClasses(ratioRaw: unknown): { className: string; ratioCss: string } {
  const raw = typeof ratioRaw === 'string' ? ratioRaw.trim().toLowerCase() : '16:9';
  const map: Record<string, { className: string; ratioCss: string }> = {
    '16:9': { className: 'aspect-video', ratioCss: '16 / 9' },
    '4:3': { className: 'aspect-[4/3]', ratioCss: '4 / 3' },
    '1:1': { className: 'aspect-square', ratioCss: '1 / 1' },
    '3:2': { className: 'aspect-[3/2]', ratioCss: '3 / 2' },
  };
  return map[raw] ?? map['16:9']!;
}

/** When models put slides in props.slides instead of Slide children (matches server normalize). */
function slideSpecToNode(spec: unknown, nodeId: string): GenUiNode {
  if (!spec || typeof spec !== 'object') {
    return { nodeId, kind: 'Slide', props: {}, children: [] };
  }
  const o = spec as Record<string, unknown>;
  const k = o.kind ?? o.type;
  if (typeof k === 'string' && k.toLowerCase() === 'slide') {
    const props =
      typeof o.props === 'object' && o.props !== null ? (o.props as Record<string, unknown>) : {};
    const children = Array.isArray(o.children) ? (o.children as GenUiNode[]) : [];
    return { nodeId, kind: 'Slide', props, children };
  }
  const { children: rawCh, content, icon, ...rest } = o;
  const props: Record<string, unknown> = { ...rest };
  if (props.layout == null && typeof props.variant === 'string') {
    const v = props.variant.toLowerCase();
    if (v === 'cover') props.layout = 'cover';
    else props.layout = 'title-content';
  }
  const children: GenUiNode[] = [];
  let idx = 0;
  if (icon != null && String(icon).trim()) {
    children.push({
      nodeId: `${nodeId}-ic-${idx++}`,
      kind: 'Icon',
      props: { name: String(icon).trim(), size: 48, color: 'primary' },
    });
  }
  if (typeof content === 'string' && content.trim()) {
    children.push({
      nodeId: `${nodeId}-tx-${idx++}`,
      kind: 'Text',
      props: { value: content.trim(), size: 'lg', color: 'muted' },
    });
  }
  if (Array.isArray(rawCh)) {
    for (const c of rawCh) {
      if (c && typeof c === 'object' && 'kind' in c) {
        const cn = c as GenUiNode;
        children.push({
          ...cn,
          nodeId: cn.nodeId || `${nodeId}-ch-${idx++}`,
        });
      }
    }
  }
  return { nodeId, kind: 'Slide', props, children };
}

function childrenFromSlideDeckProps(deck: GenUiNode): GenUiNode[] | null {
  const pr = deck.props || {};
  const raw = pr.slides;
  if (!Array.isArray(raw) || raw.length === 0) return null;
  const existing = (deck.children || []) as GenUiNode[];
  if (existing.some((c) => c.kind === 'Slide')) return null;
  return raw.map((spec, i) => slideSpecToNode(spec, `${deck.nodeId}-slide-${i}`));
}

export function SlideDeckPlayer({
  node,
  depth,
  ctx,
  renderNode,
}: {
  node: GenUiNode;
  depth: number;
  ctx: GenUiRenderContextValue;
  renderNode: (n: GenUiNode, d: number, c: GenUiRenderContextValue) => ReactNode;
}) {
  const p = (node.props || {}) as Record<string, unknown>;
  const effectiveChildren = useMemo(() => {
    const fromProps = childrenFromSlideDeckProps(node);
    return fromProps ?? ((node.children || []) as GenUiNode[]);
  }, [node]);
  const slides = useMemo(
    () => effectiveChildren.filter((c) => c.kind === 'Slide'),
    [effectiveChildren],
  );
  const pages = slides.length > 0 ? slides : effectiveChildren;
  const [index, setIndex] = useState(0);
  const deckRef = useRef<HTMLDivElement>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReducedMotion(mq.matches);
    const fn = () => setPrefersReducedMotion(mq.matches);
    mq.addEventListener('change', fn);
    return () => mq.removeEventListener('change', fn);
  }, []);

  const total = pages.length;
  const safeIndex = total > 0 ? Math.min(index, total - 1) : 0;
  const loop = b(p.loop);
  const showPager = p.showPager !== false;
  const showExport = p.showExport !== false;
  const title = s(p.title) || 'Presentation';
  const { className: aspectClass, ratioCss } = aspectClasses(p.aspectRatio);

  const go = useCallback(
    (delta: number) => {
      if (total <= 0) return;
      setIndex((i) => {
        let next = i + delta;
        if (loop) {
          next = ((next % total) + total) % total;
        } else {
          next = Math.max(0, Math.min(total - 1, next));
        }
        return next;
      });
    },
    [total, loop],
  );

  const goFirst = useCallback(() => setIndex(0), []);
  const goLast = useCallback(() => setIndex(Math.max(0, total - 1)), [total]);

  const toggleFs = useCallback(async () => {
    const el = deckRef.current;
    if (!el) return;
    try {
      if (document.fullscreenElement === el) {
        await document.exitFullscreen();
        setFullscreen(false);
      } else {
        await el.requestFullscreen();
        setFullscreen(true);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    const el = deckRef.current;
    if (!el) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.target !== el && !el.contains(e.target as Node)) return;
      switch (e.key) {
        case 'ArrowRight':
        case 'PageDown':
        case ' ':
          e.preventDefault();
          go(1);
          break;
        case 'ArrowLeft':
        case 'PageUp':
          e.preventDefault();
          go(-1);
          break;
        case 'Home':
          e.preventDefault();
          goFirst();
          break;
        case 'End':
          e.preventDefault();
          goLast();
          break;
        case 'f':
        case 'F':
          e.preventDefault();
          void toggleFs();
          break;
        case 'Escape':
          if (document.fullscreenElement === el) {
            e.preventDefault();
            void document.exitFullscreen();
          }
          break;
        default:
          break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go, goFirst, goLast, toggleFs]);

  useEffect(() => {
    const onFs = () => {
      setFullscreen(document.fullscreenElement === deckRef.current);
    };
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, []);

  const ptr = useRef<{ x: number; active: boolean }>({ x: 0, active: false });
  const onPointerDown = (e: React.PointerEvent) => {
    ptr.current = { x: e.clientX, active: true };
  };
  const onPointerUp = (e: React.PointerEvent) => {
    if (!ptr.current.active) return;
    ptr.current.active = false;
    const dx = e.clientX - ptr.current.x;
    if (Math.abs(dx) > 48) go(dx < 0 ? 1 : -1);
  };

  const treeForExport: GenUiTreeV1 = useMemo(() => {
    const synth = childrenFromSlideDeckProps(node);
    if (synth == null) {
      return { schemaVersion: '1', root: node };
    }
    const { slides: _omit, ...restProps } = (node.props || {}) as Record<string, unknown>;
    return {
      schemaVersion: '1',
      root: { ...node, children: synth, props: restProps },
    };
  }, [node]);

  const handleExportPdf = async () => {
    if (!ctx.sessionId || exporting) return;
    setExporting(true);
    try {
      await exportGenUiTreeToPdf({
        sessionId: ctx.sessionId,
        messageId: ctx.messageId,
        tree: treeForExport,
        mode: 'deck',
        pageSize: 'Slide16x9',
        orientation: 'landscape',
      });
    } catch {
      /* toast optional */
    } finally {
      setExporting(false);
    }
  };

  if (total === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border p-6 text-sm text-muted-foreground">
        Slide deck has no slides.
      </div>
    );
  }

  return (
    <div
      ref={deckRef}
      tabIndex={0}
      className="rounded-xl border border-border bg-surface-elevated shadow-soft outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-primary-500/40"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2 bg-surface-sunken/50">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground truncate">
            {title}
          </p>
          <p className="text-xs text-foreground font-medium tabular-nums">
            {safeIndex + 1} / {total}
          </p>
        </div>
        <div className="flex items-center gap-1">
          {showExport && ctx.sessionId && (
            <button
              type="button"
              onClick={() => void handleExportPdf()}
              disabled={exporting}
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-primary-700 hover:bg-primary-50 dark:text-primary-300 dark:hover:bg-primary-950/30 disabled:opacity-50"
              title="Export PDF"
            >
              <FileDown className="h-3.5 w-3.5" />
              PDF
            </button>
          )}
          <button
            type="button"
            onClick={() => void toggleFs()}
            className="rounded-lg p-1 text-muted-foreground hover:bg-surface-sunken hover:text-foreground"
            title={fullscreen ? 'Exit fullscreen (Esc)' : 'Fullscreen (F)'}
          >
            {fullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      <div
        className={cn('relative w-full bg-background', aspectClass)}
        style={{ aspectRatio: ratioCss }}
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
        onPointerLeave={() => {
          ptr.current.active = false;
        }}
        role="region"
        aria-roledescription="carousel"
        aria-label={title}
      >
        {pages.map((slide, i) => (
          <div
            key={slide.nodeId}
            className={cn(
              'absolute inset-0 overflow-hidden p-4 sm:p-6',
              prefersReducedMotion ? '' : 'transition-opacity duration-300',
              i === safeIndex ? 'z-10 opacity-100' : 'z-0 opacity-0 pointer-events-none',
            )}
            aria-hidden={i !== safeIndex}
          >
            <div className="h-full min-h-0 overflow-auto">{renderNode(slide, depth + 1, ctx)}</div>
          </div>
        ))}
      </div>

      {showPager && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-3 py-2 bg-surface-sunken/40">
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="rounded-lg p-1 text-muted-foreground hover:bg-surface-sunken"
              aria-label="First slide"
              onClick={goFirst}
            >
              <ChevronsLeft className="h-4 w-4" />
            </button>
            <button
              type="button"
              className="rounded-lg p-1 text-muted-foreground hover:bg-surface-sunken"
              aria-label="Previous slide"
              onClick={() => go(-1)}
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <button
              type="button"
              className="rounded-lg p-1 text-muted-foreground hover:bg-surface-sunken"
              aria-label="Next slide"
              onClick={() => go(1)}
            >
              <ArrowRight className="h-4 w-4" />
            </button>
            <button
              type="button"
              className="rounded-lg p-1 text-muted-foreground hover:bg-surface-sunken"
              aria-label="Last slide"
              onClick={goLast}
            >
              <ChevronsRight className="h-4 w-4" />
            </button>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-1.5">
            {pages.map((_, i) => (
              <button
                key={i}
                type="button"
                aria-label={`Go to slide ${i + 1}`}
                aria-current={i === safeIndex}
                onClick={() => setIndex(i)}
                className={cn(
                  'h-2 w-2 rounded-full transition-colors',
                  i === safeIndex ? 'bg-primary-600 scale-125' : 'bg-border hover:bg-muted-foreground/40',
                )}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
