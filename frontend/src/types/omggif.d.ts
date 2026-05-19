declare module 'omggif' {
  export class GifReader {
    constructor(buf: Uint8Array);
    numFrames(): number;
  }

  export class GifWriter {
    constructor(
      buf: Uint8Array,
      width: number,
      height: number,
      gopts?: {
        loop?: number | null;
        palette?: number[];
        background?: number;
      },
    );
    addFrame(
      x: number,
      y: number,
      w: number,
      h: number,
      indexed_pixels: Uint8Array,
      opts?: {
        palette?: number[] | null;
        delay?: number;
        transparent?: number | null;
        disposal?: number;
      },
    ): number;
    end(): number;
  }
}
