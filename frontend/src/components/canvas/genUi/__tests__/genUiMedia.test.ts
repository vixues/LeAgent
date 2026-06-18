import { describe, expect, it } from 'vitest';

import {
  buildAssetTreeFromRunState,
  formatAssetHistoryLabel,
  listAssetHistoryTrees,
  listOrderedNodeAssets,
  mediaFromNodeRunState,
  patchAssetTreeFileRef,
} from '../genUiMedia';
import type { AssetHistoryEntry } from '@/features/workflow/store/assetHistory';

describe('mediaFromNodeRunState', () => {
  it('prefers per-node metadata.file_id over gen_ui src', () => {
    const item = mediaFromNodeRunState({
      ui: {
        schemaVersion: '1',
        root: {
          kind: 'Image',
          props: { src: '/api/v1/files/wrong/preview', fileId: 'wrong' },
        },
      },
      metadata: { file_id: 'correct', kind: 'image' },
    });
    expect(item?.fileId).toBe('correct');
    expect(item?.src).toBe('/api/v1/files/correct/preview');
  });

  it('falls back to gen_ui fileId when metadata is absent', () => {
    const item = mediaFromNodeRunState({
      ui: {
        schemaVersion: '1',
        root: {
          kind: 'Image',
          props: { src: '/api/v1/files/only-ui/preview', fileId: 'only-ui' },
        },
      },
    });
    expect(item?.fileId).toBe('only-ui');
  });
});

describe('patchAssetTreeFileRef', () => {
  it('rewrites media leaves to the canonical file id', () => {
    const tree = patchAssetTreeFileRef(
      {
        schemaVersion: '1',
        root: {
          kind: 'Image',
          props: { src: '/api/v1/files/stale/preview' },
        },
      },
      'canonical-id',
      { width: 1024, height: 1024 },
    );
    const props = tree.root?.props as Record<string, unknown>;
    expect(props.fileId).toBe('canonical-id');
    expect(props.src).toBe('/api/v1/files/canonical-id/preview');
    expect(props.caption).toBe('1024×1024');
  });
});

describe('listOrderedNodeAssets', () => {
  it('builds one entry per node using metadata.file_id', () => {
    const nodes = {
      concept: {
        status: 'success' as const,
        metadata: { file_id: 'aaa', width: 1024, height: 1024 },
      },
      upscale: {
        status: 'success' as const,
        metadata: { file_id: 'bbb', width: 2048, height: 2048 },
      },
    };
    const entries = listOrderedNodeAssets(nodes, ['concept', 'upscale']);
    expect(entries).toHaveLength(2);
    expect(mediaFromNodeRunState(nodes.concept)?.fileId).toBe('aaa');
    expect(buildAssetTreeFromRunState('upscale', nodes.upscale)?.root?.children?.[1]).toMatchObject({
      kind: 'Image',
      props: expect.objectContaining({ fileId: 'bbb' }),
    });
  });
});

describe('listAssetHistoryTrees', () => {
  it('labels refine iterations and builds one tree per history entry', () => {
    const history: AssetHistoryEntry[] = [
      {
        id: 'concept:first',
        nodeId: 'concept',
        fileId: 'first',
        nodeRunIndex: 1,
        sequence: 0,
        metadata: { file_id: 'first', refine_iteration: 0, width: 1024, height: 1024 },
      },
      {
        id: 'concept:second',
        nodeId: 'concept',
        fileId: 'second',
        nodeRunIndex: 2,
        sequence: 1,
        metadata: { file_id: 'second', refine_iteration: 1, width: 1024, height: 1024 },
      },
    ];
    expect(formatAssetHistoryLabel(history[0], 'concept')).toContain('initial');
    expect(formatAssetHistoryLabel(history[1], 'concept')).toContain('refine 1');
    const trees = listAssetHistoryTrees(history, { concept: 'Concept' });
    expect(trees).toHaveLength(2);
    expect(trees[0].id).toBe('concept:first');
    expect(trees[1].id).toBe('concept:second');
    const leaf = trees[1].tree.root?.children?.[1] as { props?: { fileId?: string } };
    expect(leaf?.props?.fileId).toBe('second');
  });
});
