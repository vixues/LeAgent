import { describe, expect, it } from 'vitest';

import type { GenUiNode, GenUiTreeV1 } from '@/types/genUi';

import { outputsToGenUiTree, type WorkflowOutputSpec } from '../outputsToGenUiTree';

function onlyChild(tree: GenUiTreeV1 | null): GenUiNode {
  expect(tree).not.toBeNull();
  expect(tree!.root.children).toHaveLength(1);
  return tree!.root.children![0]!;
}

describe('outputsToGenUiTree: shape auto-detection', () => {
  it('returns null for empty outputs', () => {
    expect(outputsToGenUiTree(null)).toBeNull();
    expect(outputsToGenUiTree({})).toBeNull();
  });

  it('maps array-of-objects to a Table with the union of keys', () => {
    const node = onlyChild(
      outputsToGenUiTree({
        rows: [
          { name: 'a', score: 1 },
          { name: 'b', extra: true },
        ],
      }),
    );
    expect(node.kind).toBe('Table');
    expect(node.props?.headers).toEqual(['name', 'score', 'extra']);
    expect(node.children).toHaveLength(2);
    // Missing cells render empty, objects stringify.
    const secondRow = node.children![1]!;
    expect(secondRow.children![1]!.props?.value).toBe('');
    expect(secondRow.children![2]!.props?.value).toBe('true');
  });

  it('maps scalar arrays to a List', () => {
    const node = onlyChild(outputsToGenUiTree({ items: ['x', 'y'] }));
    expect(node.kind).toBe('List');
    expect(node.children).toHaveLength(2);
  });

  it('maps plain objects to a KeyValueList', () => {
    const node = onlyChild(outputsToGenUiTree({ summary: { total: 3, ok: true } }));
    expect(node.kind).toBe('KeyValueList');
    expect(node.props?.items).toEqual([
      { label: 'total', value: '3' },
      { label: 'ok', value: 'true' },
    ]);
  });

  it('maps numbers to Stat, booleans to Badge, text to Markdown', () => {
    expect(onlyChild(outputsToGenUiTree({ n: 42 })).kind).toBe('Stat');
    expect(onlyChild(outputsToGenUiTree({ b: false })).kind).toBe('Badge');
    expect(onlyChild(outputsToGenUiTree({ t: 'hello' })).kind).toBe('Markdown');
  });
});

describe('outputsToGenUiTree: ui hints', () => {
  it('honours render: chart with categories/series payloads', () => {
    const specs: WorkflowOutputSpec[] = [
      { name: 'sales', ui: { render: 'chart', options: { chart: 'line' } } },
    ];
    const node = onlyChild(
      outputsToGenUiTree(
        { sales: { categories: ['Q1', 'Q2'], series: [{ name: 's', values: [1, 2] }] } },
        specs,
      ),
    );
    expect(node.kind).toBe('Chart');
    expect(node.props?.chart).toBe('line');
    expect(node.props?.categories).toEqual(['Q1', 'Q2']);
    expect(node.props?.series).toEqual([{ name: 's', values: [1, 2] }]);
  });

  it('builds chart series from arrays of objects', () => {
    const specs: WorkflowOutputSpec[] = [{ name: 'm', ui: { render: 'chart' } }];
    const node = onlyChild(
      outputsToGenUiTree(
        { m: [{ month: 'Jan', revenue: 10 }, { month: 'Feb', revenue: 20 }] },
        specs,
      ),
    );
    expect(node.props?.categories).toEqual(['Jan', 'Feb']);
    expect(node.props?.series).toEqual([{ name: 'revenue', values: [10, 20] }]);
  });

  it('honours markdown / json / image hints', () => {
    const md = onlyChild(
      outputsToGenUiTree({ x: 123 }, [{ name: 'x', ui: { render: 'markdown' } }]),
    );
    expect(md.kind).toBe('Markdown');

    const json = onlyChild(
      outputsToGenUiTree({ x: { a: 1 } }, [{ name: 'x', ui: { render: 'json' } }]),
    );
    expect(json.kind).toBe('CodeBlock');
    expect(json.props?.language).toBe('json');

    const img = onlyChild(
      outputsToGenUiTree({ x: '/files/pic.png' }, [{ name: 'x', ui: { render: 'image' } }]),
    );
    expect(img.kind).toBe('Image');
    expect(img.props?.src).toBe('/files/pic.png');
  });

  it('falls back to auto-detection when a table hint does not fit', () => {
    const node = onlyChild(
      outputsToGenUiTree({ x: 'plain text' }, [{ name: 'x', ui: { render: 'table' } }]),
    );
    expect(node.kind).toBe('Markdown');
  });
});

describe('outputsToGenUiTree: composition', () => {
  it('wraps multiple outputs in titled sections', () => {
    const tree = outputsToGenUiTree({ a: 1, b: 'two' });
    expect(tree!.root.children).toHaveLength(2);
    for (const section of tree!.root.children!) {
      expect(section.kind).toBe('Stack');
      expect(section.children![0]!.kind).toBe('SectionHeader');
    }
    expect(tree!.root.children![0]!.children![0]!.props?.title).toBe('a');
  });

  it('renders explicit gen_ui trees first, verbatim', () => {
    const explicit: GenUiTreeV1 = {
      schemaVersion: '1',
      root: { nodeId: 'custom-1', kind: 'Markdown', props: { content: 'from node' } },
    };
    const tree = outputsToGenUiTree({ n: 1 }, undefined, [explicit]);
    expect(tree!.root.children).toHaveLength(2);
    expect(tree!.root.children![0]).toBe(explicit.root);
    expect(tree!.root.children![1]!.kind).toBe('Stat');
  });

  it('returns a tree from gen_ui passthrough alone', () => {
    const explicit: GenUiTreeV1 = {
      schemaVersion: '1',
      root: { nodeId: 'custom-1', kind: 'Markdown', props: { content: 'x' } },
    };
    const tree = outputsToGenUiTree({}, undefined, [explicit]);
    expect(tree!.root.children).toEqual([explicit.root]);
  });
});
