/**
 * Fenwick (binary-indexed) tree over per-row heights.
 *
 * Gives O(log n) offset<->index mapping for the conversation virtualizer so
 * scroll-to-range and cumulative-offset queries stay cheap at 10,000+ rows.
 *
 * - `offsetForIndex(i)` = sum of heights[0..i-1]
 * - `indexForOffset(px)` = index of the row containing pixel offset `px`
 * - `setHeight(i, h)` = O(log n) delta update when a row is measured
 */
export class HeightIndex {
  private n = 0;
  private tree: Float64Array = new Float64Array(1);
  private heights: Float64Array = new Float64Array(0);

  constructor(initial: number[]) {
    this.build(initial);
  }

  get size(): number {
    return this.n;
  }

  build(initial: number[]): void {
    this.n = initial.length;
    this.heights = Float64Array.from(initial);
    this.tree = new Float64Array(this.n + 1);
    // O(n) construction: each node seeds its parent.
    for (let i = 1; i <= this.n; i++) {
      this.tree[i]! += this.heights[i - 1]!;
      const parent = i + (i & -i);
      if (parent <= this.n) this.tree[parent]! += this.tree[i]!;
    }
  }

  /** Sum of the first `count` heights (clamped to [0, n]). */
  prefix(count: number): number {
    let i = Math.max(0, Math.min(count, this.n));
    let sum = 0;
    while (i > 0) {
      sum += this.tree[i]!;
      i -= i & -i;
    }
    return sum;
  }

  total(): number {
    return this.prefix(this.n);
  }

  offsetForIndex(index: number): number {
    return this.prefix(index);
  }

  getHeight(index: number): number {
    if (index < 0 || index >= this.n) return 0;
    return this.heights[index]!;
  }

  setHeight(index: number, height: number): boolean {
    if (index < 0 || index >= this.n) return false;
    const delta = height - this.heights[index]!;
    if (delta === 0) return false;
    this.heights[index] = height;
    let i = index + 1;
    while (i <= this.n) {
      this.tree[i]! += delta;
      i += i & -i;
    }
    return true;
  }

  /**
   * Largest index `i` such that `prefix(i) <= offset` — i.e. the row that
   * contains pixel `offset`. Uses Fenwick binary lifting (no linear scan).
   */
  indexForOffset(offset: number): number {
    if (this.n === 0) return 0;
    if (offset <= 0) return 0;
    let pos = 0;
    let remaining = offset;
    let pw = 1;
    while (pw << 1 <= this.n) pw <<= 1;
    for (; pw > 0; pw >>= 1) {
      const next = pos + pw;
      if (next <= this.n && this.tree[next]! <= remaining) {
        pos = next;
        remaining -= this.tree[next]!;
      }
    }
    return Math.min(pos, this.n - 1);
  }
}
