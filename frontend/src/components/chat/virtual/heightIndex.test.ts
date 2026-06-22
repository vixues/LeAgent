import { describe, it, expect } from 'vitest';
import { HeightIndex } from './heightIndex';

describe('HeightIndex', () => {
  it('computes cumulative offsets', () => {
    const hi = new HeightIndex([10, 20, 30, 40]);
    expect(hi.offsetForIndex(0)).toBe(0);
    expect(hi.offsetForIndex(1)).toBe(10);
    expect(hi.offsetForIndex(2)).toBe(30);
    expect(hi.offsetForIndex(3)).toBe(60);
    expect(hi.total()).toBe(100);
  });

  it('maps offset to the containing row index', () => {
    const hi = new HeightIndex([10, 20, 30, 40]);
    expect(hi.indexForOffset(0)).toBe(0);
    expect(hi.indexForOffset(5)).toBe(0);
    expect(hi.indexForOffset(10)).toBe(1);
    expect(hi.indexForOffset(29)).toBe(1);
    expect(hi.indexForOffset(30)).toBe(2);
    expect(hi.indexForOffset(59)).toBe(2);
    expect(hi.indexForOffset(60)).toBe(3);
    expect(hi.indexForOffset(10_000)).toBe(3);
  });

  it('applies O(log n) height corrections and updates offsets', () => {
    const hi = new HeightIndex([10, 20, 30, 40]);
    const changed = hi.setHeight(1, 25);
    expect(changed).toBe(true);
    expect(hi.getHeight(1)).toBe(25);
    expect(hi.offsetForIndex(2)).toBe(35);
    expect(hi.total()).toBe(105);
    // no-op update returns false
    expect(hi.setHeight(1, 25)).toBe(false);
  });

  it('handles empty and single-row indexes', () => {
    const empty = new HeightIndex([]);
    expect(empty.size).toBe(0);
    expect(empty.total()).toBe(0);
    expect(empty.indexForOffset(50)).toBe(0);

    const single = new HeightIndex([42]);
    expect(single.indexForOffset(0)).toBe(0);
    expect(single.indexForOffset(1000)).toBe(0);
    expect(single.total()).toBe(42);
  });

  it('matches a brute-force prefix sum over many rows', () => {
    const n = 5_000;
    const heights = Array.from({ length: n }, (_, i) => (i % 7) + 1);
    const hi = new HeightIndex(heights);
    let acc = 0;
    for (let i = 0; i < n; i++) {
      expect(hi.offsetForIndex(i)).toBe(acc);
      acc += heights[i]!;
    }
    expect(hi.total()).toBe(acc);
    // spot-check offset->index round trips
    expect(hi.indexForOffset(hi.offsetForIndex(1234))).toBe(1234);
    expect(hi.indexForOffset(hi.offsetForIndex(4999))).toBe(4999);
  });
});
