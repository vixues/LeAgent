import { GifWriter } from 'omggif';

export interface SpriteSheetToGifOptions {
  cols: number;
  rows: number;
  /** Crop pixels inside each cell */
  pad: number;
  fps: number;
  /** Use GIF transparency for pixels with alpha below threshold */
  transparent: boolean;
  /** 0 = infinite loop (Netscape extension) */
  loop: number;
  /**
   * Inclusive 0-based frame indices in left-to-right, top-to-bottom order (all cells in the grid).
   * Default: all frames. Use to export a subset (e.g. one row) for per-action clips.
   */
  frameRange?: { start: number; end: number };
}

/** Output metadata for UI and validation (logical GIF frame size = one cell inner size). */
export interface SpriteSheetGifResult {
  blob: Blob;
  sheetWidth: number;
  sheetHeight: number;
  cols: number;
  rows: number;
  pad: number;
  cellWidth: number;
  cellHeight: number;
  frameWidth: number;
  frameHeight: number;
  frameCount: number;
  remainderWidth: number;
  remainderHeight: number;
}

export type SpriteSheetGifMeta = Omit<SpriteSheetGifResult, 'blob'>;

/** Blend unpremultiplied RGBA onto white for stable 216-color quantization (avoids classifying soft AA as "transparent"). */
export function flattenRgbOnWhite(r: number, g: number, b: number, a255: number): [number, number, number] {
  const a = a255 / 255;
  return [
    Math.round(r * a + 255 * (1 - a)),
    Math.round(g * a + 255 * (1 - a)),
    Math.round(b * a + 255 * (1 - a)),
  ];
}

export interface SpriteFrameRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Grid frame rectangles in source image pixel space, left-to-right then top-to-bottom.
 */
export function computeSpriteFrameRects(
  imgW: number,
  imgH: number,
  cols: number,
  rows: number,
  pad: number,
): SpriteFrameRect[] {
  if (cols < 1 || rows < 1) throw new Error('cols and rows must be >= 1');
  const cellW = Math.floor(imgW / cols);
  const cellH = Math.floor(imgH / rows);
  if (cellW <= pad * 2 || cellH <= pad * 2) {
    throw new Error('pad too large for cell size');
  }
  const w = cellW - pad * 2;
  const h = cellH - pad * 2;
  const rects: SpriteFrameRect[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      rects.push({
        x: c * cellW + pad,
        y: r * cellH + pad,
        w,
        h,
      });
    }
  }
  return rects;
}

/** 6×6×6 web-safe cube padded to 256 entries (required by omggif). */
function web216PalettePadded256(): number[] {
  const arr: number[] = [];
  for (let ri = 0; ri < 6; ri++) {
    for (let gi = 0; gi < 6; gi++) {
      for (let bi = 0; bi < 6; bi++) {
        arr.push((ri * 51 << 16) | (gi * 51 << 8) | bi * 51);
      }
    }
  }
  while (arr.length < 256) {
    arr.push(arr[arr.length - 1] ?? 0);
  }
  return arr;
}

function nearestPaletteIndex(r: number, g: number, b: number, palette: number[]): number {
  let best = 0;
  let bestD = Infinity;
  // Only search unique web colors (first 216)
  for (let i = 0; i < 216; i++) {
    const pr = (palette[i]! >> 16) & 0xff;
    const pg = (palette[i]! >> 8) & 0xff;
    const pb = palette[i]! & 0xff;
    const d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2;
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

/**
 * Rasterize sprite sheet cells to an animated GIF Blob (global palette, optional transparency).
 */
export async function spriteSheetToGifBlob(
  img: HTMLImageElement,
  options: SpriteSheetToGifOptions,
): Promise<SpriteSheetGifResult> {
  const { cols, rows, pad, fps, transparent, loop, frameRange } = options;
  const sw = img.naturalWidth;
  const sh = img.naturalHeight;
  const cellW = Math.floor(sw / cols);
  const cellH = Math.floor(sh / rows);
  const remainderWidth = sw - cols * cellW;
  const remainderHeight = sh - rows * cellH;

  const rects = computeSpriteFrameRects(sw, sh, cols, rows, pad);
  if (rects.length < 2) {
    throw new Error('Need at least 2 frames (e.g. cols×rows ≥ 2)');
  }
  const fw = rects[0]!.w;
  const fh = rects[0]!.h;
  for (const r of rects) {
    if (r.w !== fw || r.h !== fh) {
      throw new Error('All cells must have the same inner size');
    }
  }

  let useRects: typeof rects = rects;
  if (frameRange !== undefined) {
    const { start, end } = frameRange;
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start || end >= rects.length) {
      throw new Error(
        `frameRange: invalid range [${start}, ${end}] for ${rects.length} frame(s)`,
      );
    }
    useRects = rects.slice(start, end + 1);
    if (useRects.length < 1) {
      throw new Error('frameRange: need at least 1 frame in range');
    }
  }

  const palette = web216PalettePadded256();
  const transparentIndex = 255;
  if (transparent) {
    palette[transparentIndex] = 0x010101;
  }

  const delayCs = Math.max(1, Math.round(100 / Math.max(0.1, fps)));
  const framePixels = fw * fh;
  /** Only nearly-invisible pixels become GIF-transparent; soft AA is flattened onto white first. */
  const transparentAlphaCutoff = 10;

  const scratch = document.createElement('canvas');
  scratch.width = fw;
  scratch.height = fh;
  const ctx = scratch.getContext('2d', { willReadFrequently: true });
  if (!ctx) throw new Error('Canvas unsupported');

  const buf = new Uint8Array(fw * fh * useRects.length * 3 + 200_000);
  /** Without disposal, transparent pixels composite over the previous frame and the animation looks corrupt. */
  const gif = new GifWriter(buf, fw, fh, {
    loop,
    palette,
    background: transparent ? transparentIndex : 1,
  });

  for (const rect of useRects) {
    ctx.clearRect(0, 0, fw, fh);
    ctx.drawImage(img, rect.x, rect.y, rect.w, rect.h, 0, 0, fw, fh);
    const data = ctx.getImageData(0, 0, fw, fh).data;
    const indexed = new Uint8Array(framePixels);
    for (let i = 0; i < framePixels; i++) {
      const o = i * 4;
      const a = data[o + 3]!;
      if (transparent && a < transparentAlphaCutoff) {
        indexed[i] = transparentIndex;
      } else {
        const [fr, fg, fb] = flattenRgbOnWhite(data[o]!, data[o + 1]!, data[o + 2]!, a);
        indexed[i] = nearestPaletteIndex(fr, fg, fb, palette);
      }
    }
    const frameOpts: { delay: number; transparent?: number; disposal?: number } = {
      delay: delayCs,
      ...(transparent ? { transparent: transparentIndex, disposal: 2 as const } : {}),
    };
    gif.addFrame(0, 0, fw, fh, indexed, frameOpts);
  }

  const end = gif.end();
  const blob = new Blob([buf.slice(0, end)], { type: 'image/gif' });
  return {
    blob,
    sheetWidth: sw,
    sheetHeight: sh,
    cols,
    rows,
    pad,
    cellWidth: cellW,
    cellHeight: cellH,
    frameWidth: fw,
    frameHeight: fh,
    frameCount: useRects.length,
    remainderWidth,
    remainderHeight,
  };
}

export function loadImageElement(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const el = new Image();
    // blob:/data: are same-origin; forcing anonymous on blob URLs can break canvas readback in some browsers.
    if (/^https?:\/\//i.test(src)) {
      el.crossOrigin = 'anonymous';
    }
    el.onload = () => {
      const done = () => resolve(el);
      try {
        el.decode().then(done).catch(done);
      } catch {
        done();
      }
    };
    el.onerror = () => reject(new Error('Failed to load image'));
    el.src = src;
  });
}
