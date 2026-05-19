import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import {
  Brain,
  ChevronDown,
  ChevronRight,
  History,
  Layers,
  RefreshCw,
  Route,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chat';
import { useAgentMemorySnapshot } from '@/hooks/useAgentMemorySnapshot';
import { usePromptPreview } from '@/hooks/usePromptPreview';

/** Scrollable region: no visible scrollbar, bounded height when expanded. */
const SCROLL_BODY = 'overflow-y-auto no-scrollbar';
const EXPAND_TEXT_MAX = 'max-h-[min(22rem,42vh)]';
/** Cap entire prompt inspector so memory grid stays reachable without nested giant scrollers. */
const PROMPT_SECTION_MAX = 'max-h-[min(34vh,300px)]';

function formatWhen(iso: string | null | undefined, locale: string) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '—';
    return d.toLocaleString(locale, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '—';
  }
}

function oneLinePreview(text: string, max = 96) {
  const line = text.split('\n')[0]?.trim() || text.trim();
  if (line.length <= max) return line || '—';
  return `${line.slice(0, max)}…`;
}

function ExpandableText({
  text,
  showMoreLabel,
  showLessLabel,
}: {
  text: string;
  showMoreLabel: string;
  showLessLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const long = text.length > 220 || text.split('\n').length > 4;
  if (!long) {
    return <p className="text-sm text-foreground whitespace-pre-wrap break-words">{text}</p>;
  }
  if (!open) {
    return (
      <div>
        <p className="line-clamp-4 text-sm text-foreground whitespace-pre-wrap break-words">{text}</p>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="mt-1 text-xs font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300"
        >
          {showMoreLabel}
        </button>
      </div>
    );
  }
  return (
    <div>
      <div className={cn(EXPAND_TEXT_MAX, SCROLL_BODY)}>
        <p className="text-sm text-foreground whitespace-pre-wrap break-words">{text}</p>
      </div>
      <button
        type="button"
        onClick={() => setOpen(false)}
        className="mt-1 text-xs font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300"
      >
        {showLessLabel}
      </button>
    </div>
  );
}

function SectionShell({
  title,
  icon: Icon,
  count,
  children,
  collapseLabel,
  expandLabel,
}: {
  title: string;
  icon: typeof History;
  count: number;
  children: ReactNode;
  collapseLabel: string;
  expandLabel: string;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col rounded-lg border border-border-subtle bg-background/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex flex-shrink-0 w-full items-center gap-2 border-b border-border-subtle px-3 py-2 text-left hover:bg-surface-sunken/40"
        aria-expanded={open}
      >
        <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </span>
        <span className="ml-auto rounded-full bg-surface-sunken px-2 py-0.5 text-[10px] font-semibold tabular-nums text-muted-foreground">
          {count}
        </span>
        {open ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        )}
        <span className="sr-only">{open ? collapseLabel : expandLabel}</span>
      </button>
      {open && (
        <div className={cn('min-h-0 flex-1 space-y-2 p-2', SCROLL_BODY)}>
          {children}
        </div>
      )}
    </div>
  );
}

function MemoryCard({
  preview,
  metaLine,
  titleLine,
  body,
  showMore,
  showLess,
  collapseCard,
  expandCard,
}: {
  preview: string;
  metaLine: ReactNode;
  titleLine?: ReactNode;
  body: string;
  showMore: string;
  showLess: string;
  collapseCard: string;
  expandCard: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <article className="rounded-lg border border-border-subtle bg-background/50 shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2 px-2.5 py-2 text-left hover:bg-surface-sunken/30"
        aria-expanded={open}
      >
        <span className="mt-0.5 shrink-0 text-muted-foreground">
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-mono text-[10px] text-muted-foreground-tertiary">{metaLine}</div>
          {titleLine}
          {!open && (
            <p className="mt-0.5 truncate text-xs text-muted-foreground">{oneLinePreview(preview)}</p>
          )}
        </div>
        <span className="sr-only">{open ? collapseCard : expandCard}</span>
      </button>
      {open && (
        <div className="border-t border-border-subtle px-2.5 pb-2.5 pt-1">
          <ExpandableText text={body} showMoreLabel={showMore} showLessLabel={showLess} />
        </div>
      )}
    </article>
  );
}

function PromptPreviewPanel({
  sessionId,
  onRefreshAll,
  memoryFetching,
}: {
  sessionId: string;
  onRefreshAll: () => void;
  memoryFetching: boolean;
}) {
  const { t } = useTranslation();
  const promptQuery = usePromptPreview({ sessionId, enabled: Boolean(sessionId) });
  /* Collapsed by default so episodic / semantic / procedural columns stay in view. */
  const [sectionOpen, setSectionOpen] = useState(false);
  const [layersOpen, setLayersOpen] = useState<Record<number, boolean>>({});
  /** Which layer row is most visible inside the prompt scroll region (scroll spy for outline). */
  const [activeLayerIdx, setActiveLayerIdx] = useState(0);
  const promptBodyRef = useRef<HTMLDivElement>(null);

  const layerCount = promptQuery.data?.layers.length ?? 0;
  const layerNavKey = useMemo(() => {
    const xs = promptQuery.data?.layers;
    if (!xs?.length) return '';
    return xs.map((l, i) => `${i}:${l.name}:${l.tokens ?? ''}`).join('\u001f');
  }, [promptQuery.data]);

  const onRefresh = useCallback(() => {
    void promptQuery.refetch();
    onRefreshAll();
  }, [promptQuery, onRefreshAll]);

  const fetching = promptQuery.isFetching || memoryFetching;

  const tokenStats = useMemo(() => {
    const d = promptQuery.data;
    if (!d) return null;
    const layerTokSum = d.layers.reduce((acc, l) => acc + (l.tokens ?? 0), 0);
    const approxFromChars = Math.max(0, Math.round(d.total_chars / 4));
    return {
      layerTokSum,
      layerCount: d.layers.length,
      totalChars: d.total_chars,
      approxFromChars,
    };
  }, [promptQuery.data]);

  useEffect(() => {
    setActiveLayerIdx(0);
  }, [layerCount, sessionId, promptQuery.data?.variant_key]);

  useEffect(() => {
    const root = promptBodyRef.current;
    if (!sectionOpen || !root || layerCount === 0) return;

    let obs: IntersectionObserver | undefined;
    let cancelled = false;

    const frame = requestAnimationFrame(() => {
      if (cancelled) return;
      const nodes = Array.from(root.querySelectorAll<HTMLElement>('[data-prompt-layer-index]'));
      if (nodes.length === 0 || cancelled) return;

      obs = new IntersectionObserver(
        (entries) => {
          const visible = entries.filter((e) => e.isIntersecting && e.intersectionRatio > 0);
          if (!visible.length) return;
          let best = visible[0]!;
          for (const e of visible) {
            if (e.intersectionRatio > best.intersectionRatio) best = e;
          }
          const raw = best.target.getAttribute('data-prompt-layer-index');
          const idx = raw == null ? NaN : Number(raw);
          if (!Number.isNaN(idx)) setActiveLayerIdx(idx);
        },
        {
          root,
          rootMargin: '-6% 0px -38% 0px',
          threshold: [0, 0.06, 0.14, 0.22, 0.35, 0.5, 0.65, 0.8, 1],
        },
      );
      nodes.forEach((n) => obs!.observe(n));
    });

    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      obs?.disconnect();
    };
  }, [sectionOpen, layerCount, layersOpen, layerNavKey]);

  const jumpToLayer = useCallback((idx: number) => {
    setLayersOpen((m) => ({ ...m, [idx]: true }));
    setActiveLayerIdx(idx);
    requestAnimationFrame(() => {
      const root = promptBodyRef.current;
      if (!root) return;
      const el = root.querySelector(`[data-prompt-layer-index="${idx}"]`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }, []);

  const expandAllLayers = useCallback(() => {
    if (layerCount === 0) return;
    setLayersOpen(() => {
      const next: Record<number, boolean> = {};
      for (let i = 0; i < layerCount; i++) next[i] = true;
      return next;
    });
  }, [layerCount]);

  const collapseAllLayers = useCallback(() => {
    setLayersOpen({});
  }, []);

  return (
    <div className="min-h-0 w-full shrink-0 rounded-lg border border-border-subtle bg-background/40">
      <div className="sticky top-0 z-30 flex flex-col border-b border-border-subtle bg-surface/95 backdrop-blur-sm">
        <div className="flex flex-shrink-0 items-center gap-2 px-3 py-2">
          <button
            type="button"
            onClick={() => setSectionOpen((v) => !v)}
            className="flex min-w-0 flex-1 items-center gap-2 text-left"
            aria-expanded={sectionOpen}
          >
            {sectionOpen ? (
              <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            )}
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {t('chat.workspace.memory.promptPreview.title', { defaultValue: 'System prompt (preview)' })}
            </span>
          </button>
          <button
            type="button"
            onClick={onRefresh}
            disabled={fetching}
            className="inline-flex shrink-0 items-center gap-1 rounded-md border border-border-subtle bg-surface px-2 py-1 text-[10px] font-medium text-foreground hover:bg-surface-sunken disabled:opacity-50"
          >
            <RefreshCw className={cn('h-3 w-3', fetching && 'animate-spin')} />
            {t('chat.workspace.memory.refresh', { defaultValue: 'Refresh' })}
          </button>
        </div>
        {sectionOpen && tokenStats && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 border-t border-border-subtle/80 px-3 py-1.5 font-mono text-[10px] leading-tight text-muted-foreground">
            <span className="tabular-nums" title={t('chat.workspace.memory.promptPreview.layerTokensHint', { defaultValue: 'Sum of per-layer token estimates from the builder' })}>
              {t('chat.workspace.memory.promptPreview.layerTokens', { defaultValue: 'Layer Σ' })}: {tokenStats.layerTokSum}
            </span>
            <span>
              {t('chat.workspace.memory.promptPreview.layerCount', {
                count: tokenStats.layerCount,
                defaultValue: '{{count}} layers',
              })}
            </span>
            <span className="tabular-nums">
              {t('chat.workspace.memory.promptPreview.chars', { defaultValue: 'Chars' })}: {tokenStats.totalChars}
            </span>
            <span className="tabular-nums text-muted-foreground-tertiary" title={t('chat.workspace.memory.promptPreview.approxHint', { defaultValue: 'Rough tokens from system text length (chars÷4)' })}>
              ~{t('chat.workspace.memory.promptPreview.approxTokens', { defaultValue: 'tok' })}: {tokenStats.approxFromChars}
            </span>
          </div>
        )}
      </div>
      {sectionOpen && (
        <div
          ref={promptBodyRef}
          className={cn(
            'min-h-0 space-y-2 overscroll-contain p-3',
            SCROLL_BODY,
            PROMPT_SECTION_MAX,
          )}
        >
          {promptQuery.isError && (
            <p className="text-xs text-destructive">
              {t('chat.workspace.memory.promptPreview.loadError', {
                defaultValue: 'Could not load prompt preview.',
              })}
            </p>
          )}
          {promptQuery.isLoading && !promptQuery.data && (
            <p className="text-xs text-muted-foreground">
              {t('chat.workspace.memory.loading', { defaultValue: 'Loading…' })}
            </p>
          )}
          {promptQuery.data && (
            <>
              <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px] text-muted-foreground-tertiary">
                <span>
                  {t('chat.workspace.memory.promptPreview.query', { defaultValue: 'Query' })}:{' '}
                  {promptQuery.data.query_used
                    ? oneLinePreview(promptQuery.data.query_used, 120)
                    : t('chat.workspace.memory.promptPreview.emptyQuery', { defaultValue: '(empty)' })}
                </span>
                <span className="max-w-full truncate" title={promptQuery.data.variant_key}>
                  {promptQuery.data.variant_key}
                </span>
              </div>
              <div className="rounded-md border border-border-subtle bg-surface/80 p-2">
                <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-foreground">
                  {promptQuery.data.system_text || '—'}
                </pre>
              </div>
              {promptQuery.data.layers.length > 0 && (
                <div className="space-y-2">
                  <nav
                    className="sticky top-0 z-20 -mx-3 border-b border-border-subtle bg-background/92 px-3 py-2 shadow-[0_1px_0_0_hsl(var(--border-subtle)/0.35)] backdrop-blur-md"
                    aria-label={t('chat.workspace.memory.promptPreview.layerOutline', {
                      defaultValue: 'Outline',
                    })}
                    title={t('chat.workspace.memory.promptPreview.layerOutlineHint', {
                      defaultValue: 'Jump to a prompt layer; highlights follow scroll position',
                    })}
                  >
                    <div className="mb-1.5 flex min-w-0 items-center justify-between gap-2">
                      <p className="min-w-0 truncate text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                        {t('chat.workspace.memory.promptPreview.layers', { defaultValue: 'Layers' })}
                        <span className="ml-1.5 font-mono normal-case text-muted-foreground-tertiary">
                          ({String(activeLayerIdx + 1).padStart(2, '0')}/{String(layerCount).padStart(2, '0')})
                        </span>
                      </p>
                      <div className="flex shrink-0 gap-1">
                        <button
                          type="button"
                          onClick={expandAllLayers}
                          className="rounded border border-border-subtle bg-surface/80 px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground hover:bg-surface-sunken/60 hover:text-foreground"
                        >
                          {t('chat.workspace.memory.promptPreview.expandAllLayers', {
                            defaultValue: 'Expand all',
                          })}
                        </button>
                        <button
                          type="button"
                          onClick={collapseAllLayers}
                          className="rounded border border-border-subtle bg-surface/80 px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground hover:bg-surface-sunken/60 hover:text-foreground"
                        >
                          {t('chat.workspace.memory.promptPreview.collapseAllLayers', {
                            defaultValue: 'Collapse all',
                          })}
                        </button>
                      </div>
                    </div>
                    <div className="flex gap-1 overflow-x-auto pb-0.5 no-scrollbar">
                      {promptQuery.data.layers.map((layer, idx) => {
                        const isActive = activeLayerIdx === idx;
                        const isOpen = layersOpen[idx] ?? false;
                        return (
                          <button
                            key={`nav-${layer.name}-${idx}`}
                            type="button"
                            onClick={() => jumpToLayer(idx)}
                            className={cn(
                              'inline-flex max-w-[11rem] shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-left text-[10px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50',
                              isActive
                                ? 'border-primary-500/45 bg-primary-500/12 text-foreground'
                                : 'border-border-subtle bg-background/70 text-muted-foreground hover:bg-surface-sunken/55 hover:text-foreground',
                            )}
                            aria-current={isActive ? 'location' : undefined}
                            title={t('chat.workspace.memory.promptPreview.jumpToLayer', {
                              name: layer.name,
                              tokens: layer.tokens ?? 0,
                              defaultValue: `Jump to ${layer.name} · ${layer.tokens ?? 0} tok`,
                            })}
                          >
                            <span className="shrink-0 font-mono text-[9px] text-muted-foreground-tertiary">
                              {String(idx + 1).padStart(2, '0')}
                            </span>
                            <span className="min-w-0 flex-1 truncate">{layer.name}</span>
                            {isOpen ? (
                              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary-500/80" aria-hidden />
                            ) : (
                              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/25" aria-hidden />
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </nav>
                  <ul className="space-y-1">
                    {promptQuery.data.layers.map((layer, idx) => {
                      const isLo = layersOpen[idx] ?? false;
                      return (
                        <li
                          key={`${layer.name}-${idx}`}
                          data-prompt-layer-index={idx}
                          className="scroll-mt-[5.75rem] overflow-hidden rounded border border-border-subtle bg-background/50"
                        >
                          <button
                            type="button"
                            onClick={() =>
                              setLayersOpen((m) => ({
                                ...m,
                                [idx]: !isLo,
                              }))
                            }
                            className="flex w-full min-w-0 items-center gap-2 border-b border-border-subtle bg-background/90 px-2 py-1.5 text-left text-[10px] font-medium text-foreground hover:bg-surface-sunken/45"
                          >
                            {isLo ? (
                              <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
                            ) : (
                              <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
                            )}
                            <span className="w-5 shrink-0 text-center font-mono text-[9px] text-muted-foreground-tertiary">
                              {String(idx + 1).padStart(2, '0')}
                            </span>
                            <span className="min-w-0 flex-1 truncate" title={layer.name}>
                              {layer.name}
                            </span>
                            <span className="shrink-0 tabular-nums text-muted-foreground">
                              {layer.tokens} tok
                              {layer.truncated
                                ? ` · ${t('chat.workspace.memory.promptPreview.truncated', { defaultValue: 'trunc' })}`
                                : ''}
                            </span>
                          </button>
                          {isLo && (
                            <div
                              className={cn(
                                'border-t border-border-subtle px-2 py-2',
                                SCROLL_BODY,
                                'max-h-[min(18rem,32vh)]',
                              )}
                            >
                              <pre className="whitespace-pre-wrap break-words font-mono text-[10px] text-muted-foreground">
                                {layer.body || '—'}
                              </pre>
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function ContextMemoryTab() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const locale = i18n.language || 'en-US';

  const query = useAgentMemorySnapshot({
    sessionId: currentSessionId,
    enabled: Boolean(currentSessionId),
  });

  const onRefreshAll = useCallback(() => {
    void query.refetch();
    if (currentSessionId) {
      void queryClient.invalidateQueries({ queryKey: ['prompt-preview', currentSessionId] });
    }
  }, [query, queryClient, currentSessionId]);

  const totalCount = useMemo(() => {
    if (!query.data) return 0;
    return (
      query.data.episodes.length +
      query.data.facts.length +
      query.data.procedures.length
    );
  }, [query.data]);

  if (!currentSessionId) {
    return (
      <div className="flex h-full min-h-0 flex-1 basis-0 flex-col items-center justify-center px-6 text-center text-sm text-muted-foreground">
        <Brain className="mb-2 h-8 w-8 opacity-40" aria-hidden />
        <p>{t('chat.workspace.memory.noSession', { defaultValue: 'Select or start a chat to view agent memory.' })}</p>
      </div>
    );
  }

  const showMore = t('chat.workspace.memory.showMore', { defaultValue: 'Show more' });
  const showLess = t('chat.workspace.memory.showLess', { defaultValue: 'Show less' });
  const collapseSection = t('chat.workspace.memory.collapseSection', { defaultValue: 'Collapse section' });
  const expandSection = t('chat.workspace.memory.expandSection', { defaultValue: 'Expand section' });
  const collapseCard = t('chat.workspace.memory.collapseCard', { defaultValue: 'Collapse' });
  const expandCard = t('chat.workspace.memory.expandCard', { defaultValue: 'Expand' });

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 basis-0 flex-col overflow-hidden px-3 pb-3 pt-0">
      <div className="flex flex-shrink-0 flex-col gap-2 border-b border-border-subtle pb-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">
              {t('chat.workspace.memory.title', { defaultValue: 'Context memory' })}
            </h3>
            {query.data && !query.data.enabled && (
              <span className="rounded-full border border-border-subtle bg-surface-sunken px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                {t('chat.workspace.memory.memoryOff', { defaultValue: 'Memory unavailable' })}
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {t('chat.workspace.memory.subtitle', {
              defaultValue: 'What the agent may recall for this session: past turns, facts, and procedure patterns.',
            })}
          </p>
        </div>
        <button
          type="button"
          onClick={onRefreshAll}
          disabled={query.isFetching}
          className="inline-flex flex-shrink-0 items-center justify-center gap-1.5 rounded-md border border-border-subtle bg-surface px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-surface-sunken disabled:opacity-50"
        >
          <RefreshCw className={cn('h-3.5 w-3.5', query.isFetching && 'animate-spin')} />
          {t('chat.workspace.memory.refresh', { defaultValue: 'Refresh' })}
        </button>
      </div>

      {/* One scroll viewport: prompt preview + memory columns scroll together so layers / stores stay reachable. */}
      <div className="flex min-h-0 min-w-0 flex-1 basis-0 flex-col overflow-y-auto no-scrollbar overscroll-contain pt-1">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
        <PromptPreviewPanel
          sessionId={currentSessionId}
          onRefreshAll={onRefreshAll}
          memoryFetching={query.isFetching}
        />

        {query.isError && (
          <div className="flex-shrink-0 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
            {t('chat.workspace.memory.loadError', { defaultValue: 'Could not load memory. Try again.' })}
          </div>
        )}

        {query.isLoading && !query.data && (
          <div className="flex min-h-[8rem] flex-1 items-center justify-center text-xs text-muted-foreground">
            {t('chat.workspace.memory.loading', { defaultValue: 'Loading…' })}
          </div>
        )}

        {query.data && (
          <div className="grid min-h-0 min-w-0 shrink-0 grid-cols-1 gap-2 lg:flex-1 lg:grid-cols-3 lg:gap-3 lg:items-stretch lg:[grid-auto-rows:minmax(0,1fr)]">
            <SectionShell
            title={t('chat.workspace.memory.episodic', { defaultValue: 'Episodic' })}
            icon={History}
            count={query.data.episodes.length}
            collapseLabel={collapseSection}
            expandLabel={expandSection}
          >
            {query.data.episodes.length === 0 ? (
              <p className="px-1 py-4 text-center text-xs text-muted-foreground">
                {t('chat.workspace.memory.emptyEpisodic', { defaultValue: 'No turn summaries stored yet.' })}
              </p>
            ) : (
              query.data.episodes.map((ep) => (
                <MemoryCard
                  key={ep.id}
                  preview={ep.summary}
                  metaLine={
                    <>
                      {formatWhen(ep.created_at, locale)}
                      {ep.recall_count > 0
                        ? ` · ${t('chat.workspace.memory.recalls', { count: ep.recall_count, defaultValue: '{{count}}× recalled' })}`
                        : ''}
                    </>
                  }
                  body={ep.summary}
                  showMore={showMore}
                  showLess={showLess}
                  collapseCard={collapseCard}
                  expandCard={expandCard}
                />
              ))
            )}
            </SectionShell>

            <SectionShell
            title={t('chat.workspace.memory.semantic', { defaultValue: 'Semantic' })}
            icon={Layers}
            count={query.data.facts.length}
            collapseLabel={collapseSection}
            expandLabel={expandSection}
          >
            {query.data.facts.length === 0 ? (
              <p className="px-1 py-4 text-center text-xs text-muted-foreground">
                {t('chat.workspace.memory.emptySemantic', { defaultValue: 'No durable facts yet.' })}
              </p>
            ) : (
              query.data.facts.map((fact) => (
                <MemoryCard
                  key={fact.id}
                  preview={`${fact.key}: ${fact.value}`}
                  metaLine={
                    <>
                      {formatWhen(fact.created_at, locale)}
                      {fact.source ? ` · ${fact.source}` : ''}
                      {` · ${Math.round((fact.confidence ?? 0) * 100)}%`}
                    </>
                  }
                  titleLine={<p className="text-xs font-semibold text-foreground">{fact.key}</p>}
                  body={fact.value}
                  showMore={showMore}
                  showLess={showLess}
                  collapseCard={collapseCard}
                  expandCard={expandCard}
                />
              ))
            )}
            </SectionShell>

            <SectionShell
            title={t('chat.workspace.memory.procedural', { defaultValue: 'Procedural' })}
            icon={Route}
            count={query.data.procedures.length}
            collapseLabel={collapseSection}
            expandLabel={expandSection}
          >
            {query.data.procedures.length === 0 ? (
              <p className="px-1 py-4 text-center text-xs text-muted-foreground">
                {t('chat.workspace.memory.emptyProcedural', { defaultValue: 'No procedure patterns recorded yet.' })}
              </p>
            ) : (
              query.data.procedures.map((proc) => (
                <MemoryCard
                  key={proc.id}
                  preview={proc.description}
                  metaLine={
                    <>
                      {formatWhen(proc.last_run_at || proc.created_at, locale)}
                      {` · ${Math.round((proc.success_rate ?? 0) * 100)}% ${t('chat.workspace.memory.success', { defaultValue: 'success' })}`}
                      {proc.run_count > 0 ? ` · ${proc.run_count}×` : ''}
                    </>
                  }
                  titleLine={<p className="text-xs font-semibold text-foreground">{proc.name}</p>}
                  body={proc.description}
                  showMore={showMore}
                  showLess={showLess}
                  collapseCard={collapseCard}
                  expandCard={expandCard}
                />
              ))
            )}
            </SectionShell>
          </div>
        )}

        {query.data && totalCount > 0 && (
          <p className="flex-shrink-0 pb-1 text-center text-[10px] text-muted-foreground-tertiary">
            {t('chat.workspace.memory.footerHint', {
              defaultValue: '{{count}} items across episodic, semantic, and procedural stores.',
              count: totalCount,
            })}
          </p>
        )}
        </div>
      </div>
    </div>
  );
}
