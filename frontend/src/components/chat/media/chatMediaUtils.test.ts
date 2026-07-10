import { describe, expect, it } from 'vitest';
import {
  extractApiFileDownloadId,
  extractApiFilePreviewId,
  extractAuthedApiFilePreviewId,
  isChatRenderableImageSrc,
  isInvalidApiFilePreviewRef,
  managedFilePreviewHasSignedToken,
  resolveMarkdownImageSrcFromAttachments,
} from './chatMediaUtils';

const id = '123e4567-e89b-42d3-a456-426614174000';

describe('chatMediaUtils file preview parsing', () => {
  it('extracts UUID preview ids from managed file URLs', () => {
    expect(extractApiFilePreviewId(`/api/v1/files/${id}/preview`)).toBe(id);
    expect(extractApiFilePreviewId(`http://localhost:8000/api/v1/files/${id}/preview?x=1`)).toBe(id);
  });

  it('does not fetch signed preview URLs with bearer auth', () => {
    const signed = `/api/v1/files/${id}/preview?token=signed`;
    expect(extractApiFilePreviewId(signed)).toBe(id);
    expect(extractAuthedApiFilePreviewId(signed)).toBeNull();
  });

  it('extracts file ids from download URLs with tokens', () => {
    const id = '1c40885c-f84e-42d1-9eee-60be0e9b6586';
    expect(extractApiFileDownloadId(`/api/v1/files/${id}/download?token=signed`)).toBe(id);
  });

  it('detects signed managed preview URLs for browser-first display', () => {
    const signed = `/api/v1/files/${id}/preview?token=signed`;
    expect(managedFilePreviewHasSignedToken(signed)).toBe(true);
    expect(managedFilePreviewHasSignedToken(`/api/v1/files/${id}/preview`)).toBe(false);
    expect(managedFilePreviewHasSignedToken('https://cdn.example.com/x.png?token=1')).toBe(false);
  });

  it('marks non-UUID managed preview paths as invalid', () => {
    const invalid = '/api/v1/files/paper_airplane_flowchart/preview?redirect=1';
    expect(extractApiFilePreviewId(invalid)).toBeNull();
    expect(extractAuthedApiFilePreviewId(invalid)).toBeNull();
    expect(isInvalidApiFilePreviewRef(invalid)).toBe(true);
  });
});

describe('resolveMarkdownImageSrcFromAttachments', () => {
  const id = '123e4567-e89b-42d3-a456-426614174000';
  const signed = `/api/v1/files/${id}/preview?token=signed`;

  it('rewrites bare filenames to the matching attachment preview URL', () => {
    expect(
      resolveMarkdownImageSrcFromAttachments('sde_animation.gif', [
        { id, name: 'sde_animation.gif', previewUrl: signed },
      ]),
    ).toBe(signed);
  });

  it('matches by basename when markdown uses a subpath', () => {
    expect(
      resolveMarkdownImageSrcFromAttachments('out/plot.png', [
        { id, name: 'workspace/out/plot.png', previewUrl: signed },
      ]),
    ).toBe(signed);
  });

  it('prefers the last attachment when basenames collide', () => {
    const second = `/api/v1/files/223e4567-e89b-42d3-a456-426614174001/preview?token=b`;
    expect(
      resolveMarkdownImageSrcFromAttachments('plot.png', [
        { id, name: 'plot.png', previewUrl: signed },
        { id: '223e4567-e89b-42d3-a456-426614174001', name: 'plot.png', previewUrl: second },
      ]),
    ).toBe(second);
  });

  it('falls back to authed preview path when URLs are absent', () => {
    expect(resolveMarkdownImageSrcFromAttachments('x.gif', [{ id, name: 'x.gif' }])).toBe(
      `/api/v1/files/${id}/preview`,
    );
  });

  it('uses alt text as a filename fallback when markdown src is empty', () => {
    expect(
      resolveMarkdownImageSrcFromAttachments('', [
        { id, name: '3d_rose.gif', previewUrl: signed },
      ], '3d_rose.gif'),
    ).toBe(signed);
  });

  it('resolves assistant inline media by filename', () => {
    expect(
      resolveMarkdownImageSrcFromAttachments('3d_rose.gif', [
        {
          id,
          name: '3d_rose.gif',
          previewUrl: signed,
          downloadUrl: `/api/v1/files/${id}/download?token=signed`,
        },
      ]),
    ).toBe(signed);
  });

  it('does not rewrite managed file preview refs', () => {
    expect(resolveMarkdownImageSrcFromAttachments(signed, [{ id, name: 'other.gif' }])).toBe(signed);
  });

  it('does not rewrite http(s) URLs', () => {
    expect(
      resolveMarkdownImageSrcFromAttachments('https://cdn.example.com/a.png', [
        { id, name: 'a.png', previewUrl: signed },
      ]),
    ).toBe('https://cdn.example.com/a.png');
  });
});

describe('isChatRenderableImageSrc', () => {
  const id = '123e4567-e89b-42d3-a456-426614174000';

  it('accepts managed preview URLs and remote images', () => {
    expect(isChatRenderableImageSrc(`/api/v1/files/${id}/preview?token=x`)).toBe(true);
    expect(isChatRenderableImageSrc('https://cdn.example.com/a.png')).toBe(true);
    expect(isChatRenderableImageSrc('data:image/png;base64,abc')).toBe(true);
  });

  it('rejects unresolved bare filenames that would 404 locally', () => {
    expect(isChatRenderableImageSrc('placeholder.png')).toBe(false);
    expect(isChatRenderableImageSrc('out/plot.png')).toBe(false);
  });

  it('rejects known external placeholder hosts', () => {
    expect(isChatRenderableImageSrc('https://i.imgur.com/placeholder.png')).toBe(false);
    expect(isChatRenderableImageSrc('https://via.placeholder.com/150')).toBe(false);
  });
});
