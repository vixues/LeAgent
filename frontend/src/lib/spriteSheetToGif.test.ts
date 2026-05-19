import { describe, it, expect } from 'vitest';
import { GifReader, GifWriter } from 'omggif';
import { computeSpriteFrameRects } from './spriteSheetToGif';

describe('computeSpriteFrameRects', () => {
  it('returns row-major rects with pad', () => {
    const rects = computeSpriteFrameRects(512, 512, 4, 4, 0);
    expect(rects).toHaveLength(16);
    expect(rects[0]).toEqual({ x: 0, y: 0, w: 128, h: 128 });
    expect(rects[1]).toEqual({ x: 128, y: 0, w: 128, h: 128 });
    expect(rects[4]).toEqual({ x: 0, y: 128, w: 128, h: 128 });
  });

  it('applies inner pad', () => {
    const rects = computeSpriteFrameRects(400, 200, 2, 1, 10);
    expect(rects).toHaveLength(2);
    expect(rects[0]).toEqual({ x: 10, y: 10, w: 180, h: 180 });
    expect(rects[1]).toEqual({ x: 210, y: 10, w: 180, h: 180 });
  });
});

describe('GIF animation (omggif)', () => {
  it('encodes at least two frames (same pipeline family as sprite export)', () => {
    const palette: number[] = [];
    for (let i = 0; i < 256; i++) {
      palette.push((i << 16) | (i << 8) | i);
    }
    const buf = new Uint8Array(40_000);
    const gw = new GifWriter(buf, 4, 4, { loop: 0, palette, background: 1 });
    const frameA = new Uint8Array(16).fill(10);
    const frameB = new Uint8Array(16).fill(200);
    gw.addFrame(0, 0, 4, 4, frameA, { delay: 8 });
    gw.addFrame(0, 0, 4, 4, frameB, { delay: 8 });
    const end = gw.end();
    const reader = new GifReader(buf.subarray(0, end));
    expect(reader.numFrames()).toBeGreaterThanOrEqual(2);
  });
});
