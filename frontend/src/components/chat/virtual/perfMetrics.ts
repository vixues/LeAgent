/**
 * Lightweight chat-rendering instrumentation.
 *
 * Dev-only counters for the conversation virtualizer and streaming hot paths.
 * Kept allocation-free in production: every record call short-circuits unless
 * `import.meta.env.DEV` is set. Exposed on `window.__leagentChatMetrics` so a
 * profiling session can read render amplification, height-correction churn, and
 * mounted-row counts without wiring a UI.
 */

interface ChatRenderMetrics {
  /** Times the virtual range (mounted window) changed. */
  rangeUpdates: number;
  /** ResizeObserver-driven height corrections applied to the height index. */
  heightCorrections: number;
  /** Scroll-anchor compensations applied to avoid above-viewport jumps. */
  anchorAdjustments: number;
  /** Largest single height correction observed (px). */
  maxCorrectionPx: number;
  /** Most recent mounted (windowed) row count. */
  mountedRows: number;
  /** Most recent total row count backing the index. */
  totalRows: number;
}

const metrics: ChatRenderMetrics = {
  rangeUpdates: 0,
  heightCorrections: 0,
  anchorAdjustments: 0,
  maxCorrectionPx: 0,
  mountedRows: 0,
  totalRows: 0,
};

const DEV = Boolean(import.meta.env?.DEV);

export function recordHeightCorrection(magnitudePx: number): void {
  if (!DEV) return;
  metrics.heightCorrections += 1;
  if (magnitudePx > metrics.maxCorrectionPx) metrics.maxCorrectionPx = magnitudePx;
}

export function recordAnchorAdjustment(): void {
  if (!DEV) return;
  metrics.anchorAdjustments += 1;
}

export function recordRangeUpdate(mountedRows: number, totalRows: number): void {
  if (!DEV) return;
  metrics.rangeUpdates += 1;
  metrics.mountedRows = mountedRows;
  metrics.totalRows = totalRows;
}

export function getChatRenderMetrics(): Readonly<ChatRenderMetrics> {
  return metrics;
}

if (DEV && typeof window !== 'undefined') {
  (window as unknown as { __leagentChatMetrics?: () => Readonly<ChatRenderMetrics> }).__leagentChatMetrics =
    getChatRenderMetrics;
}
