import { describe, expect, it } from 'vitest';
import {
  pickCanvasPreviewPathFromMetadata,
  resolveCanvasPreviewUrl,
  resolveCodingProjectPreviewHref,
} from './previewUrl';

const SAMPLE_ID = '21ef7460-a27a-428c-891a-81a34e226925';
const SAMPLE_TOKEN = 'abc.def';
const WRONG_ORIGIN = `https://leagent.dev/api/v1/coding-projects/${SAMPLE_ID}/preview/?token=${SAMPLE_TOKEN}`;
const RELATIVE = `/api/v1/coding-projects/${SAMPLE_ID}/preview/?token=${SAMPLE_TOKEN}`;

describe('pickCanvasPreviewPathFromMetadata', () => {
  it('prefers previewPath then preview_path', () => {
    expect(
      pickCanvasPreviewPathFromMetadata({
        preview_path: '/api/v1/canvas/preview?token=a',
      }),
    ).toBe('/api/v1/canvas/preview?token=a');
    expect(
      pickCanvasPreviewPathFromMetadata({
        previewPath: '/a',
        preview_path: '/b',
      }),
    ).toBe('/a');
  });

  it('accepts preview_url', () => {
    expect(
      pickCanvasPreviewPathFromMetadata({
        preview_url: 'https://example.com/p',
      }),
    ).toBe('https://example.com/p');
  });

  it('returns null when missing', () => {
    expect(pickCanvasPreviewPathFromMetadata({})).toBeNull();
    expect(pickCanvasPreviewPathFromMetadata(undefined)).toBeNull();
  });
});

describe('resolveCanvasPreviewUrl', () => {
  it('leaves absolute paths starting with /', () => {
    expect(resolveCanvasPreviewUrl('/api/v1/canvas/preview?token=x')).toBe(
      '/api/v1/canvas/preview?token=x',
    );
  });
});

describe('resolveCodingProjectPreviewHref', () => {
  it('strips a foreign origin when api base is relative (default dev proxy)', () => {
    expect(resolveCodingProjectPreviewHref(WRONG_ORIGIN, '/api/v1')).toBe(RELATIVE);
  });

  it('rehosts onto an absolute API base', () => {
    expect(
      resolveCodingProjectPreviewHref(WRONG_ORIGIN, 'http://127.0.0.1:7860/api/v1'),
    ).toBe(`http://127.0.0.1:7860${RELATIVE}`);
  });

  it('leaves unrelated https URLs unchanged', () => {
    expect(resolveCodingProjectPreviewHref('https://example.com/doc', '/api/v1')).toBe(
      'https://example.com/doc',
    );
  });

  it('leaves relative non-preview API paths unchanged', () => {
    expect(resolveCodingProjectPreviewHref('/api/v1/health', '/api/v1')).toBe('/api/v1/health');
  });
});
