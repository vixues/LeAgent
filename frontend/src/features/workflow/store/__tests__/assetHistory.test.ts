import { describe, expect, it } from 'vitest';

import {
  appendAssetHistoryEntry,
  assetVersionCount,
  type AssetHistoryEntry,
} from '../assetHistory';

function entry(nodeId: string, fileId: string, refine?: number): AssetHistoryEntry {
  return {
    id: `${nodeId}:${fileId}`,
    nodeId,
    fileId,
    nodeRunIndex: 1,
    sequence: 0,
    metadata: refine != null ? { refine_iteration: refine } : undefined,
  };
}

describe('appendAssetHistoryEntry', () => {
  it('appends unique files per node and increments nodeRunIndex', () => {
    let history: AssetHistoryEntry[] = [];
    history = appendAssetHistoryEntry(history, 'concept', {
      fileId: 'aaa',
      metadata: { refine_iteration: 0 },
    });
    history = appendAssetHistoryEntry(history, 'concept', {
      fileId: 'bbb',
      metadata: { refine_iteration: 1 },
    });
    expect(history).toHaveLength(2);
    expect(history[0].nodeRunIndex).toBe(1);
    expect(history[1].nodeRunIndex).toBe(2);
    expect(assetVersionCount(history, 'concept')).toBe(2);
  });

  it('dedupes by fileId', () => {
    let history: AssetHistoryEntry[] = [];
    history = appendAssetHistoryEntry(history, 'concept', { fileId: 'aaa' });
    history = appendAssetHistoryEntry(history, 'concept', { fileId: 'aaa' });
    expect(history).toHaveLength(1);
  });
});

describe('assetVersionCount', () => {
  it('counts only matching node id', () => {
    const history = [
      entry('concept', 'a'),
      entry('upscale', 'b'),
      entry('concept', 'c'),
    ];
    expect(assetVersionCount(history, 'concept')).toBe(2);
    expect(assetVersionCount(history, 'upscale')).toBe(1);
  });
});
