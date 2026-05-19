import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { exportGenUiTreeToPdf } from './useGenUiExportPdf';
import type { GenUiTreeV1 } from '@/types/genUi';

const tree: GenUiTreeV1 = {
  schemaVersion: '1',
  root: { nodeId: 'r', kind: 'Stack', children: [] },
};

describe('exportGenUiTreeToPdf', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['%PDF'], { type: 'application/pdf' }),
      headers: { get: () => null },
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('defaults to A4 portrait for document mode when pageSize omitted', async () => {
    await exportGenUiTreeToPdf({ sessionId: 's1', tree, mode: 'document' });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(init).toBeDefined();
    const body = JSON.parse(init!.body as string);
    expect(body.page_size).toBe('A4');
    expect(body.orientation).toBe('portrait');
  });

  it('defaults to Slide16x9 landscape for deck mode when pageSize omitted', async () => {
    await exportGenUiTreeToPdf({ sessionId: 's1', tree, mode: 'deck' });
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(init).toBeDefined();
    const body = JSON.parse(init!.body as string);
    expect(body.page_size).toBe('Slide16x9');
    expect(body.orientation).toBe('landscape');
  });
});
