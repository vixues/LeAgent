import { describe, expect, it } from 'vitest';
import { flattenRgbOnWhite } from '@/lib/spriteSheetToGif';

describe('flattenRgbOnWhite', () => {
  it('returns white for fully transparent input', () => {
    expect(flattenRgbOnWhite(10, 20, 30, 0)).toEqual([255, 255, 255]);
  });

  it('returns original RGB for fully opaque input', () => {
    expect(flattenRgbOnWhite(10, 20, 30, 255)).toEqual([10, 20, 30]);
  });

  it('blends toward white for partial alpha', () => {
    // alpha=128/255 ≈ 0.5019; blending black onto white yields ~127 (rounded).
    expect(flattenRgbOnWhite(0, 0, 0, 128)).toEqual([127, 127, 127]);
  });
});
