import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation } from '@tanstack/react-query';
import { queryClient } from '@/lib/queryClient';
import { useChatStore } from '@/stores/chat';
import { usePromptPreview } from '@/hooks/usePromptPreview';
import { useDefaultModel, useProviders } from '@/hooks/useAdmin';
import { resolveContextBudgetTokens } from '@/lib/contextBudget';
import { apiClient } from '@/api/client';
import { cn } from '@/lib/utils';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/Popover';
import { Button } from '@/components/ui/Button';
import type { Message } from '@/types/chat';

/** Stable fallback — never use inline ``[]`` in a Zustand selector (new ref every render → infinite loop). */
const EMPTY_MESSAGES: Message[] = [];

function ContextUsageRing({
  pct,
  size = 22,
  strokeWidth = 2.5,
}: {
  pct: number;
  size?: number;
  strokeWidth?: number;
}) {
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const clamped = Math.min(100, Math.max(0, pct));
  const offset = c * (1 - clamped / 100);
  const strokeClass =
    clamped >= 85
      ? 'stroke-red-500 dark:stroke-red-400 group-hover:stroke-red-300 dark:group-hover:stroke-red-300'
      : clamped >= 60
        ? 'stroke-amber-500 dark:stroke-amber-400 group-hover:stroke-amber-300 dark:group-hover:stroke-amber-300'
        : 'stroke-emerald-500 dark:stroke-emerald-400 group-hover:stroke-emerald-300 dark:group-hover:stroke-emerald-300';

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="shrink-0 -rotate-90 transition-colors duration-200"
      aria-hidden
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        className="stroke-border-subtle transition-colors duration-200 group-hover:stroke-neutral-300 dark:group-hover:stroke-neutral-300"
        strokeWidth={strokeWidth}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        className={cn(strokeClass, 'transition-all duration-300 ease-out')}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={offset}
      />
    </svg>
  );
}

function formatTok(n: number | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString();
}

/** Per attached image — matches backend ``_VISION_BLOCK_APPROX_TOKENS`` budget heuristic (~512). */
const APPROX_VISION_TOKENS_PER_IMAGE = 512;

/** Rough token estimate for visible transcript (aligned with backend ``approximate_message_content_tokens``). */
function approximateThreadTokensFromMessages(messages: Message[]): number {
  let total = 0;
  for (const m of messages) {
    const c = m.content;
    if (typeof c === 'string' && c.length) total += Math.floor(c.length / 3);
    // Only user uploads count as vision context; assistant attachments are usually
    // tool/code outputs (workspace_attachments) and should not inflate the ring.
    const atts = m.role === 'user' ? m.attachments : undefined;
    if (atts?.length) {
      for (const a of atts) {
        const kind = a.kind?.toLowerCase();
        const mime = a.type?.toLowerCase() ?? '';
        if (kind === 'image' || mime.startsWith('image/')) {
          total += APPROX_VISION_TOKENS_PER_IMAGE;
        }
      }
    }
    if (m.thinking && m.thinking.length) total += Math.floor(m.thinking.length / 3);
    const calls = m.toolCalls;
    if (!calls?.length) continue;
    for (const tc of calls) {
      if (tc.result === undefined || tc.result === null) continue;
      try {
        const s = typeof tc.result === 'string' ? tc.result : JSON.stringify(tc.result);
        total += Math.floor(s.length / 3);
      } catch {
        total += Math.floor(String(tc.result).length / 3);
      }
    }
  }
  return total;
}

export function ContextUsagePopover({
  className,
  modelId = 'auto',
}: {
  className?: string;
  /** Composer model selector value (`auto` or `provider/model`). */
  modelId?: string;
}) {
  const { t } = useTranslation();
  const { data: providers } = useProviders();
  const { data: defaultModel } = useDefaultModel();
  const contextBudgetTokens = useMemo(
    () => resolveContextBudgetTokens(modelId, providers, defaultModel),
    [modelId, providers, defaultModel],
  );
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  /** Avoid GET …/prompt-preview before GET /chat/sessions reconciles persisted thread ids (404 spam). */
  const sessionsSynced = useChatStore((s) => s.synced);
  const messages = useChatStore((s) => {
    const sid = s.currentSessionId;
    if (!sid) return EMPTY_MESSAGES;
    return s.messages[sid] ?? EMPTY_MESSAGES;
  });
  const [open, setOpen] = useState(false);

  const { data: preview, isLoading: previewLoading } = usePromptPreview({
    sessionId: currentSessionId,
    enabled: Boolean(currentSessionId && sessionsSynced),
  });

  const lastAssistantUsage = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (!m) continue;
      if (m.role === 'assistant' && m.usage) return m.usage;
    }
    return undefined;
  }, [messages]);

  const layerTokens = useMemo(() => {
    if (!preview?.layers?.length) return undefined;
    return preview.layers.reduce((acc, l) => acc + (l.tokens ?? 0), 0);
  }, [preview]);

  const threadEstimate = useMemo(
    () => approximateThreadTokensFromMessages(messages),
    [messages],
  );

  const displayMain = useMemo(() => {
    const pt = lastAssistantUsage?.prompt_tokens;
    if (pt != null && Number.isFinite(pt) && pt > 0) return pt;

    const approx = preview?.approx_context_tokens;
    if (approx != null && Number.isFinite(approx) && approx > 0) return approx;

    const layerSum = layerTokens ?? 0;
    // When SessionManager transcript is empty on the server, ``approx_context_tokens`` can be 0
    // while layer sums still reflect the system prompt — ``??`` would wrongly freeze on 0 and skip fallbacks.
    const layersPlusThread = layerSum + threadEstimate;
    if (layersPlusThread > 0) return layersPlusThread;

    if (layerSum > 0) return layerSum;
    if (threadEstimate > 0) return threadEstimate;

    if (approx != null && Number.isFinite(approx)) return approx;
    if (pt != null && Number.isFinite(pt)) return pt;

    const tt = lastAssistantUsage?.total_tokens;
    if (tt != null && Number.isFinite(tt) && tt > 0) return tt;

    return undefined;
  }, [
    lastAssistantUsage?.prompt_tokens,
    lastAssistantUsage?.total_tokens,
    preview?.approx_context_tokens,
    layerTokens,
    threadEstimate,
  ]);

  const cacheHit = lastAssistantUsage?.prompt_cache_hit_tokens;
  const cacheMiss = lastAssistantUsage?.prompt_cache_miss_tokens;
  const cacheRatio =
    cacheHit != null && cacheMiss != null && cacheHit + cacheMiss > 0
      ? Math.round((100 * cacheHit) / (cacheHit + cacheMiss))
      : undefined;

  const usagePct = useMemo(() => {
    if (displayMain == null || !Number.isFinite(displayMain)) return 0;
    if (contextBudgetTokens <= 0) return 0;
    return (displayMain / contextBudgetTokens) * 100;
  }, [displayMain, contextBudgetTokens]);

  const compactMut = useMutation({
    mutationFn: async () => {
      if (!currentSessionId) throw new Error('no session');
      return apiClient.post<{
        applied: boolean;
        approx_tokens_before: number;
        approx_tokens_after: number;
      }>(`/chat/sessions/${currentSessionId}/compact-context`, { force_llm: false });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['prompt-preview', currentSessionId] });
      setOpen(false);
    },
  });

  const disabled = !currentSessionId || compactMut.isPending;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        type="button"
        disabled={!currentSessionId}
        className={cn(
          'group inline-flex items-center justify-center rounded-full p-1 min-w-8 min-h-8',
          'disabled:opacity-40 disabled:cursor-not-allowed',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40 focus-visible:ring-offset-2 focus-visible:ring-offset-background',
          className,
        )}
        aria-label={t('chat.contextUsageButtonAria', { defaultValue: 'Context usage' })}
        title={
          displayMain != null
            ? `${formatTok(displayMain)} / ${formatTok(contextBudgetTokens)} · ${Math.round(Math.min(100, usagePct))}%`
            : t('chat.contextUsageButtonAria', { defaultValue: 'Context usage' })
        }
      >
        <ContextUsageRing pct={usagePct} />
        <span className="sr-only">
          {displayMain != null
            ? t('chat.contextUsageSrPercent', {
                pct: Math.round(Math.min(100, usagePct)),
                tokens: formatTok(displayMain),
                defaultValue: '{{pct}}% context, {{tokens}} tokens',
              })
            : t('chat.contextUsageSrUnknown', { defaultValue: 'Context usage unknown' })}
        </span>
      </PopoverTrigger>
      <PopoverContent side="top" align="end" className="w-80 max-h-[min(24rem,70vh)] overflow-y-auto">
        <div className="space-y-3 text-xs">
          <div className="font-semibold text-foreground">
            {t('chat.contextUsageTitle', { defaultValue: 'Context' })}
          </div>

          <div className="flex justify-between gap-2">
            <span className="text-muted-foreground-tertiary">
              {t('chat.contextUsageBudget', { defaultValue: 'Model context window' })}
            </span>
            <span className="tabular-nums">{formatTok(contextBudgetTokens)}</span>
          </div>
          <div className="flex justify-between gap-2">
            <span className="text-muted-foreground-tertiary">
              {t('chat.contextUsageEstimated', { defaultValue: 'Estimated in context' })}
            </span>
            <span className="tabular-nums">
              {displayMain != null ? (
                <>
                  {formatTok(displayMain)}
                  <span className="text-muted-foreground-tertiary ml-1">
                    ({Math.round(Math.min(100, usagePct))}%)
                  </span>
                </>
              ) : (
                '—'
              )}
            </span>
          </div>

          {previewLoading && open ? (
            <p className="text-muted-foreground-tertiary">{t('common.loading')}</p>
          ) : null}

          {preview?.layers?.length ? (
            <div>
              <div className="text-muted-foreground-tertiary mb-1">
                {t('chat.contextUsageLayers', { defaultValue: 'System prompt layers' })}
              </div>
              <ul className="space-y-0.5 max-h-28 overflow-y-auto">
                {preview.layers.map((layer) => (
                  <li key={layer.name} className="flex justify-between gap-2">
                    <span className="truncate text-muted-foreground">{layer.name}</span>
                    <span className="tabular-nums shrink-0">{formatTok(layer.tokens)}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-1 flex justify-between border-t border-border-subtle pt-1 font-medium">
                <span>{t('chat.contextUsageLayersSum', { defaultValue: 'Layers total' })}</span>
                <span className="tabular-nums">{formatTok(layerTokens)}</span>
              </div>
            </div>
          ) : null}

          <div className="flex justify-between gap-2 border-t border-border-subtle pt-2">
            <span className="text-muted-foreground-tertiary">
              {t('chat.contextUsageLastPrompt', { defaultValue: 'Last turn prompt tokens' })}
            </span>
            <span className="tabular-nums">{formatTok(lastAssistantUsage?.prompt_tokens)}</span>
          </div>

          {cacheHit != null || cacheMiss != null ? (
            <>
              <div className="flex justify-between gap-2">
                <span className="text-muted-foreground-tertiary">
                  {t('chat.contextUsageCacheHit', { defaultValue: 'KV cache hit' })}
                </span>
                <span className="tabular-nums">{formatTok(cacheHit)}</span>
              </div>
              <div className="flex justify-between gap-2">
                <span className="text-muted-foreground-tertiary">
                  {t('chat.contextUsageCacheMiss', { defaultValue: 'KV cache miss' })}
                </span>
                <span className="tabular-nums">{formatTok(cacheMiss)}</span>
              </div>
              {cacheRatio != null ? (
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground-tertiary">
                    {t('chat.contextUsageCacheRatio', { defaultValue: 'Hit ratio' })}
                  </span>
                  <span className="tabular-nums">{cacheRatio}%</span>
                </div>
              ) : null}
            </>
          ) : null}

          <Button
            type="button"
            variant="primary"
            size="sm"
            className="w-full mt-1"
            disabled={disabled}
            onClick={() => compactMut.mutate()}
          >
            {compactMut.isPending
              ? t('chat.contextUsageCompressing', { defaultValue: 'Compressing…' })
              : t('chat.contextUsageCompress', { defaultValue: 'Compress context' })}
          </Button>

          {compactMut.isError ? (
            <p className="text-red-600 dark:text-red-400 text-[11px]">
              {(compactMut.error as Error)?.message ?? t('chat.errors.genericRetry')}
            </p>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  );
}
