import { describe, expect, it } from 'vitest';

import { useExecutionOverlay } from '../executionOverlay';

describe('executionOverlay per-node isolation', () => {
  it('keeps independent metadata and ui per node id', () => {
    useExecutionOverlay.getState().reset();
    const pid = 'prompt-a';
    useExecutionOverlay.getState().start(pid);

    useExecutionOverlay.getState().setNode(pid, 'concept', {
      status: 'success',
      metadata: { file_id: 'aaa', kind: 'image' },
      ui: {
        schemaVersion: '1',
        root: {
          nodeId: 'img-root',
          kind: 'Image',
          props: { src: '/api/v1/files/aaa/preview', fileId: 'aaa' },
        },
      },
    });
    useExecutionOverlay.getState().setNode(pid, 'upscale', {
      status: 'success',
      metadata: { file_id: 'bbb', kind: 'image', width: 2048, height: 2048 },
      ui: {
        schemaVersion: '1',
        root: {
          nodeId: 'img-root',
          kind: 'Image',
          props: { src: '/api/v1/files/bbb/preview', fileId: 'bbb' },
        },
      },
    });

    useExecutionOverlay.getState().touchNodeAsset(pid, 'concept');
    useExecutionOverlay.getState().touchNodeAsset(pid, 'upscale');

    const overlay = useExecutionOverlay.getState().getOverlay(pid);
    expect(overlay?.nodes.concept?.metadata?.file_id).toBe('aaa');
    expect(overlay?.nodes.upscale?.metadata?.file_id).toBe('bbb');
    expect(overlay?.assetOrder).toEqual(['concept', 'upscale']);

    // Mutating one node's metadata must not affect the other.
    const conceptMeta = overlay?.nodes.concept?.metadata;
    if (conceptMeta) conceptMeta.file_id = 'mutated';
    expect(overlay?.nodes.upscale?.metadata?.file_id).toBe('bbb');
  });

  it('appendAssetHistory keeps chronological refine versions', () => {
    useExecutionOverlay.getState().reset();
    const pid = 'prompt-refine';
    useExecutionOverlay.getState().start(pid);

    useExecutionOverlay.getState().appendAssetHistory(pid, 'concept', {
      fileId: 'first',
      metadata: { refine_iteration: 0, file_id: 'first' },
    });
    useExecutionOverlay.getState().appendAssetHistory(pid, 'concept', {
      fileId: 'second',
      metadata: { refine_iteration: 1, file_id: 'second' },
    });

    const overlay = useExecutionOverlay.getState().getOverlay(pid);
    expect(overlay?.assetHistory).toHaveLength(2);
    expect(overlay?.assetHistory[0]!.fileId).toBe('first');
    expect(overlay?.assetHistory[1]!.fileId).toBe('second');
    expect(overlay?.assetOrder).toEqual(['concept']);
  });
});
