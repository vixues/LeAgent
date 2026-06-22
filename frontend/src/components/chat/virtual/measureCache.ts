/**
 * Module-level measured-height cache keyed by message id.
 *
 * Survives row unmount and session switching so re-entering a thread (or
 * scrolling a row back into the window) restores the exact prior height
 * instead of falling back to an estimate. Bounded with a simple FIFO cap so
 * very long-lived sessions cannot grow it without limit.
 */
const MAX_ENTRIES = 20_000;
const cache = new Map<string, number>();

export const measureCache = {
  get(id: string): number | undefined {
    return cache.get(id);
  },
  set(id: string, height: number): void {
    if (cache.size >= MAX_ENTRIES) {
      const oldest = cache.keys().next().value;
      if (oldest !== undefined) cache.delete(oldest);
    }
    cache.set(id, height);
  },
  has(id: string): boolean {
    return cache.has(id);
  },
};
