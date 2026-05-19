import { describe, it, expect } from 'vitest';

import {
  buildLayoutedFlow,
  extractWorkflowEdges,
  layoutNodes,
  type EngineNode,
} from './workflowLayout';
import type { FlowNode } from '@/stores/flow';

function node(id: string, overrides: Partial<FlowNode> = {}): FlowNode {
  return {
    id,
    type: 'generic',
    position: { x: 0, y: 0 },
    data: {
      label: id,
      icon: 'tool_call',
      category: 'web',
      parameters: {},
      inputs: ['input'],
      outputs: ['output'],
    },
    ...overrides,
  } as FlowNode;
}

describe('extractWorkflowEdges', () => {
  it('emits edges for linear next chains', () => {
    const nodes: EngineNode[] = [
      { id: 'start', type: 'start', next: 'a' },
      { id: 'a', type: 'tool_call', next: 'b' },
      { id: 'b', type: 'tool_call', next: 'end' },
      { id: 'end', type: 'end' },
    ];
    const edges = extractWorkflowEdges(nodes);
    expect(edges.map((e) => [e.source, e.target])).toEqual([
      ['start', 'a'],
      ['a', 'b'],
      ['b', 'end'],
    ]);
  });

  it('emits condition + else branches with condition label', () => {
    const edges = extractWorkflowEdges([
      { id: 'start', type: 'start', next: 'check' },
      {
        id: 'check',
        type: 'condition',
        conditions: [{ if: '${x} > 0', then: 'yes' }],
        else_node: 'no',
      },
      { id: 'yes', type: 'transform' },
      { id: 'no', type: 'transform' },
    ]);
    const byTarget = Object.fromEntries(edges.map((e) => [e.target, e]));
    expect(byTarget.yes?.kind).toBe('condition');
    expect(byTarget.no?.kind).toBe('else');
  });

  it('fans out parallel branches and sequences branch bodies', () => {
    const edges = extractWorkflowEdges([
      { id: 'start', type: 'start', next: 'split' },
      {
        id: 'split',
        type: 'parallel',
        branches: [
          { id: 'left', nodes: ['l1', 'l2'] },
          { id: 'right', nodes: ['r1'] },
        ],
        next: 'merge',
      },
      { id: 'l1', type: 'tool_call' },
      { id: 'l2', type: 'tool_call' },
      { id: 'r1', type: 'tool_call' },
      { id: 'merge', type: 'transform' },
    ]);
    const pairs = new Set(edges.map((e) => `${e.source}->${e.target}:${e.kind}`));
    expect(pairs.has('split->l1:branch')).toBe(true);
    expect(pairs.has('split->r1:branch')).toBe(true);
    expect(pairs.has('l1->l2:sequence')).toBe(true);
    expect(pairs.has('split->merge:next')).toBe(true);
  });

  it('extracts human-review actions and on_reject', () => {
    const edges = extractWorkflowEdges([
      { id: 'start', type: 'start', next: 'review' },
      {
        id: 'review',
        type: 'human_review',
        actions: [
          { id: 'approve', label: 'Approve', next: 'approved' },
          { id: 'reject', label: 'Reject', next: 'rejected' },
        ],
        on_reject: 'rejected',
      },
      { id: 'approved', type: 'transform' },
      { id: 'rejected', type: 'transform' },
    ]);
    const kinds = new Map(edges.map((e) => [`${e.source}->${e.target}`, e.kind]));
    expect(kinds.get('review->approved')).toBe('action');
    expect(kinds.get('review->rejected')).toBeDefined();
  });

  it('reads canonical control blocks too', () => {
    const edges = extractWorkflowEdges([
      {
        id: 'start',
        class_type: 'StartNode',
        control: { next: 'end' },
      },
      { id: 'end', class_type: 'EndNode' },
    ]);
    expect(edges).toEqual([
      expect.objectContaining({ source: 'start', target: 'end', kind: 'next' }),
    ]);
  });
});

describe('layoutNodes', () => {
  it('spreads a linear chain along the X axis in LR mode', () => {
    const nodes = [node('a'), node('b'), node('c')];
    const edges = [
      { id: 'e1', source: 'a', target: 'b', type: 'default' },
      { id: 'e2', source: 'b', target: 'c', type: 'default' },
    ];
    const { nodes: laid } = layoutNodes(nodes, edges, { direction: 'LR' });
    const xs = laid.map((n) => n.position.x);
    expect(xs[0]!).toBeLessThan(xs[1]!);
    expect(xs[1]!).toBeLessThan(xs[2]!);
  });

  it('returns an empty result for empty input', () => {
    const { nodes: laid } = layoutNodes([], []);
    expect(laid).toEqual([]);
  });

  it('ignores edges referencing unknown nodes', () => {
    const nodes = [node('a'), node('b')];
    const edges = [
      { id: 'e1', source: 'a', target: 'b', type: 'default' },
      { id: 'ghost', source: 'a', target: 'nonexistent', type: 'default' },
    ];
    const { nodes: laid } = layoutNodes(nodes, edges);
    expect(laid).toHaveLength(2);
  });
});

describe('buildLayoutedFlow', () => {
  it('produces unique positions for every node in a parallel workflow', () => {
    const { nodes, edges } = buildLayoutedFlow([
      { id: 'start', type: 'start', next: 'split' },
      {
        id: 'split',
        type: 'parallel',
        branches: [
          { id: 'left', nodes: ['l1', 'l2'] },
          { id: 'right', nodes: ['r1'] },
        ],
        next: 'merge',
      },
      { id: 'l1', type: 'tool_call' },
      { id: 'l2', type: 'tool_call' },
      { id: 'r1', type: 'tool_call' },
      { id: 'merge', type: 'transform' },
    ]);
    const seen = new Set<string>();
    for (const n of nodes) {
      const key = `${Math.round(n.position.x)},${Math.round(n.position.y)}`;
      expect(seen.has(key)).toBe(false);
      seen.add(key);
    }
    expect(edges.length).toBeGreaterThan(0);
  });

  it('handles back-edges via wait nodes without flattening the layout', () => {
    const { nodes } = buildLayoutedFlow([
      { id: 'start', type: 'start', next: 'collect' },
      { id: 'collect', type: 'tool_call', next: 'check' },
      {
        id: 'check',
        type: 'condition',
        conditions: [{ if: '${ok}', then: 'end' }],
        else_node: 'wait_more',
      },
      { id: 'wait_more', type: 'wait', next: 'collect' },
      { id: 'end', type: 'end' },
    ]);
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    expect(byId.collect!.position.x).toBeLessThan(byId.check!.position.x);
    expect(byId.check!.position.x).toBeLessThan(byId.end!.position.x);
  });
});
