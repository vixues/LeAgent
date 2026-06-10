import { describe, expect, it } from 'vitest';

import type { GenUiTreeV1 } from '@/types/genUi';

import { applyJsonPatches } from './genUi';

function tree(): GenUiTreeV1 {
  return {
    schemaVersion: '1',
    root: {
      nodeId: 'root',
      kind: 'Stack',
      props: { gap: 8 },
      children: [
        { nodeId: 'a', kind: 'Markdown', props: { content: 'first' } },
        { nodeId: 'b', kind: 'Stat', props: { label: 'count', value: '1' } },
      ],
    },
  };
}

describe('applyJsonPatches', () => {
  it('replaces nested values at arbitrary depths', () => {
    const next = applyJsonPatches(tree(), [
      { op: 'replace', path: '/root/children/1/props/value', value: '2' },
    ]);
    expect(next.root.children![1]!.props?.value).toBe('2');
  });

  it('adds object keys and appends to arrays with -', () => {
    const next = applyJsonPatches(tree(), [
      { op: 'add', path: '/root/props/direction', value: 'row' },
      {
        op: 'add',
        path: '/root/children/-',
        value: { nodeId: 'c', kind: 'Badge', props: { value: 'new' } },
      },
    ]);
    expect(next.root.props?.direction).toBe('row');
    expect(next.root.children).toHaveLength(3);
    expect(next.root.children![2]!.nodeId).toBe('c');
  });

  it('inserts into arrays at a numeric index', () => {
    const next = applyJsonPatches(tree(), [
      {
        op: 'add',
        path: '/root/children/1',
        value: { nodeId: 'mid', kind: 'Divider' },
      },
    ]);
    expect(next.root.children!.map((c) => c.nodeId)).toEqual(['a', 'mid', 'b']);
  });

  it('removes object keys and array elements', () => {
    const next = applyJsonPatches(tree(), [
      { op: 'remove', path: '/root/children/0' },
      { op: 'remove', path: '/root/props/gap' },
    ]);
    expect(next.root.children!.map((c) => c.nodeId)).toEqual(['b']);
    expect(next.root.props).toEqual({});
  });

  it('replaces the whole root', () => {
    const next = applyJsonPatches(tree(), [
      {
        op: 'replace',
        path: '/root',
        value: { nodeId: 'r2', kind: 'Markdown', props: { content: 'swapped' } },
      },
    ]);
    expect(next.root.nodeId).toBe('r2');
  });

  it('decodes RFC-6901 escaped pointer tokens', () => {
    const doc = {
      schemaVersion: '1',
      root: {
        nodeId: 'root',
        kind: 'Stack',
        props: { 'a/b': 1, 'c~d': 2 },
      },
    } as unknown as GenUiTreeV1;
    const next = applyJsonPatches(doc, [
      { op: 'replace', path: '/root/props/a~1b', value: 10 },
      { op: 'replace', path: '/root/props/c~0d', value: 20 },
    ]);
    expect(next.root.props).toEqual({ 'a/b': 10, 'c~d': 20 });
  });

  it('skips invalid patches without mutating the source', () => {
    const source = tree();
    const next = applyJsonPatches(source, [
      { op: 'replace', path: 'no-leading-slash', value: 1 },
      { op: 'replace', path: '/root/children/99/props', value: {} },
      { op: 'add', path: '/root/children/banana', value: {} },
      { op: 'replace', path: '/root/children/0/props/content', value: 'patched' },
    ]);
    // Valid trailing patch still applied; invalid ones ignored.
    expect(next.root.children![0]!.props?.content).toBe('patched');
    // Source untouched (cloned before mutation).
    expect(source.root.children![0]!.props?.content).toBe('first');
  });

  it('applies patches sequentially in order', () => {
    const next = applyJsonPatches(tree(), [
      { op: 'remove', path: '/root/children/0' },
      { op: 'replace', path: '/root/children/0/props/label', value: 'renamed' },
    ]);
    // After removal, index 0 is the former 'b' node.
    expect(next.root.children![0]!.nodeId).toBe('b');
    expect(next.root.children![0]!.props?.label).toBe('renamed');
  });
});
