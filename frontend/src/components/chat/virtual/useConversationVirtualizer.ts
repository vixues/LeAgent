import { useCallback, useLayoutEffect, useEffect, useReducer, useRef, type RefObject } from 'react';
import type { Message } from '@/types/chat';
import { HeightIndex } from './heightIndex';
import { estimateRowHeight } from './estimateRowHeight';
import { measureCache } from './measureCache';
import {
  recordAnchorAdjustment,
  recordHeightCorrection,
  recordRangeUpdate,
} from './perfMetrics';
import type { VirtualItem, VirtualRange } from './types';

interface UseConversationVirtualizerOptions {
  scrollRef: RefObject<HTMLElement | null>;
  messages: Message[];
  enabled: boolean;
  /** Extra pixels mounted above/below the viewport. Velocity-aware at runtime. */
  overscanPx?: number;
  /** When true, height corrections above the viewport are NOT compensated
   * (the list is pinned to the bottom, so growth should push content up). */
  tailLockedRef: RefObject<boolean>;
}

interface UseConversationVirtualizerResult {
  virtualItems: VirtualItem[];
  totalHeight: number;
  registerRow: (id: string) => (el: HTMLElement | null) => void;
}

const BASE_OVERSCAN = 800;
const FAST_OVERSCAN = 1600;

function structuralSignature(messages: Message[]): string {
  const n = messages.length;
  if (n === 0) return '0';
  return `${n}|${messages[0]!.id}|${messages[n - 1]!.id}`;
}

export function useConversationVirtualizer({
  scrollRef,
  messages,
  enabled,
  overscanPx,
  tailLockedRef,
}: UseConversationVirtualizerOptions): UseConversationVirtualizerResult {
  const [, forceRender] = useReducer((c: number) => c + 1, 0);

  const indexRef = useRef<HeightIndex | null>(null);
  const idToIndexRef = useRef<Map<string, number>>(new Map());
  const sigRef = useRef<string>('');
  const rangeRef = useRef<VirtualRange>({ start: 0, end: 0 });

  const rowElsRef = useRef<Map<string, HTMLElement>>(new Map());
  const rowCbRef = useRef<Map<string, (el: HTMLElement | null) => void>>(new Map());
  const observerRef = useRef<ResizeObserver | null>(null);
  const pendingMeasureRef = useRef<Set<string>>(new Set());
  const measureRafRef = useRef<number | null>(null);
  const rangeRafRef = useRef<number | null>(null);

  const lastScrollTopRef = useRef(0);
  const overscanRef = useRef(overscanPx ?? BASE_OVERSCAN);

  // Build (or rebuild) the height index when the message structure changes.
  // Runs in render but only mutates refs — never calls setState here.
  if (enabled) {
    const sig = structuralSignature(messages);
    if (sigRef.current !== sig || indexRef.current === null) {
      const heights = messages.map(
        (m) => measureCache.get(m.id) ?? estimateRowHeight(m),
      );
      indexRef.current = new HeightIndex(heights);
      const map = new Map<string, number>();
      for (let i = 0; i < messages.length; i++) map.set(messages[i]!.id, i);
      idToIndexRef.current = map;
      sigRef.current = sig;
    }
  }

  const computeRange = useCallback((): VirtualRange | null => {
    const hi = indexRef.current;
    const el = scrollRef.current;
    if (!hi || !el || hi.size === 0) return null;
    const scrollTop = el.scrollTop;
    const overscan = overscanRef.current;
    const start = hi.indexForOffset(scrollTop - overscan);
    const end = hi.indexForOffset(scrollTop + el.clientHeight + overscan);
    return { start: Math.max(0, start), end: Math.min(hi.size - 1, end) };
  }, [scrollRef]);

  const applyRange = useCallback(() => {
    const next = computeRange();
    if (!next) return;
    const prev = rangeRef.current;
    if (next.start !== prev.start || next.end !== prev.end) {
      rangeRef.current = next;
      recordRangeUpdate(next.end - next.start + 1, indexRef.current?.size ?? 0);
      forceRender();
    }
  }, [computeRange]);

  const scheduleRangeUpdate = useCallback(() => {
    if (rangeRafRef.current != null) return;
    rangeRafRef.current = requestAnimationFrame(() => {
      rangeRafRef.current = null;
      applyRange();
    });
  }, [applyRange]);

  const flushMeasures = useCallback(() => {
    measureRafRef.current = null;
    const hi = indexRef.current;
    const el = scrollRef.current;
    const pending = pendingMeasureRef.current;
    if (!hi || !el || pending.size === 0) {
      pending.clear();
      return;
    }
    const idToIndex = idToIndexRef.current;
    const scrollTop = el.scrollTop;
    const anchorIndex = hi.indexForOffset(scrollTop);
    let aboveDelta = 0;
    let changed = false;

    for (const id of pending) {
      const node = rowElsRef.current.get(id);
      const index = idToIndex.get(id);
      if (!node || index === undefined) continue;
      const measured = node.offsetHeight;
      if (measured <= 0) continue;
      const old = hi.getHeight(index);
      const delta = measured - old;
      if (Math.abs(delta) < 0.5) continue;
      if (hi.setHeight(index, measured)) {
        measureCache.set(id, measured);
        recordHeightCorrection(Math.abs(delta));
        changed = true;
        if (index < anchorIndex && !tailLockedRef.current) aboveDelta += delta;
      }
    }
    pending.clear();
    if (!changed) return;

    // Compensate scroll so content above the anchor never visibly jumps.
    if (aboveDelta !== 0) {
      el.scrollTop = scrollTop + aboveDelta;
      recordAnchorAdjustment();
    }
    // Heights (and therefore tops / total) changed — re-render the window.
    applyRange();
    forceRender();
  }, [applyRange, scrollRef, tailLockedRef]);

  const scheduleMeasureFlush = useCallback(() => {
    if (measureRafRef.current != null) return;
    measureRafRef.current = requestAnimationFrame(flushMeasures);
  }, [flushMeasures]);

  // Single shared ResizeObserver for all mounted rows.
  useEffect(() => {
    if (!enabled || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const id = (entry.target as HTMLElement).dataset.virtualRowId;
        if (id) pendingMeasureRef.current.add(id);
      }
      scheduleMeasureFlush();
    });
    observerRef.current = ro;
    return () => {
      ro.disconnect();
      observerRef.current = null;
    };
  }, [enabled, scheduleMeasureFlush]);

  // Stable per-id ref callback (cached so React does not churn observe/unobserve).
  const registerRow = useCallback((id: string) => {
    let cb = rowCbRef.current.get(id);
    if (!cb) {
      cb = (el: HTMLElement | null) => {
        const ro = observerRef.current;
        const prev = rowElsRef.current.get(id);
        if (el) {
          if (prev && prev !== el) ro?.unobserve(prev);
          el.dataset.virtualRowId = id;
          rowElsRef.current.set(id, el);
          ro?.observe(el);
          pendingMeasureRef.current.add(id);
          scheduleMeasureFlush();
        } else if (prev) {
          ro?.unobserve(prev);
          rowElsRef.current.delete(id);
        }
      };
      rowCbRef.current.set(id, cb);
    }
    return cb;
  }, [scheduleMeasureFlush]);

  // Scroll + resize listeners on the scroll container.
  useEffect(() => {
    if (!enabled) return;
    const el = scrollRef.current;
    if (!el) return;

    const onScroll = () => {
      const dy = Math.abs(el.scrollTop - lastScrollTopRef.current);
      lastScrollTopRef.current = el.scrollTop;
      overscanRef.current = dy > 40 ? FAST_OVERSCAN : (overscanPx ?? BASE_OVERSCAN);
      scheduleRangeUpdate();
    };
    el.addEventListener('scroll', onScroll, { passive: true });

    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(() => scheduleRangeUpdate());
      ro.observe(el);
    }
    return () => {
      el.removeEventListener('scroll', onScroll);
      ro?.disconnect();
    };
  }, [enabled, scrollRef, scheduleRangeUpdate, overscanPx]);

  // Recompute the range after structure changes and on first layout.
  useLayoutEffect(() => {
    if (!enabled) return;
    applyRange();
  }, [enabled, applyRange, messages.length]);

  const hi = indexRef.current;
  const totalHeight = enabled && hi ? hi.total() : 0;

  const virtualItems: VirtualItem[] = [];
  if (enabled && hi) {
    const { start, end } = rangeRef.current;
    const upper = Math.min(end, messages.length - 1);
    for (let i = start; i <= upper; i++) {
      const message = messages[i];
      if (!message) continue;
      virtualItems.push({
        index: i,
        id: message.id,
        top: hi.offsetForIndex(i),
        message,
      });
    }
  }

  return { virtualItems, totalHeight, registerRow };
}
