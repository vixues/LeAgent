import { describe, expect, it } from 'vitest';

import {
  controlFlowEdgeData,
  isControlFlowConnection,
  isStartInputFeedConnection,
  isWorkflowConnectionValid,
} from '../connectionUtils';
import type { NodeDefinition } from '../objectInfo';

const defs: Record<string, NodeDefinition> = {
  StartNode: {
    type: 'StartNode',
    displayName: 'Start',
    category: 'workflow/control',
    description: '',
    isOutputNode: false,
    controlFlow: true,
    deprecated: false,
    experimental: false,
    inputs: [],
    outputs: [{ id: 'inputs', type: 'OBJECT', color: '#ccc', isList: false }],
    metadata: {},
  },
  'Agent.test': {
    type: 'Agent.test',
    displayName: 'Agent',
    category: 'agents',
    description: '',
    isOutputNode: false,
    controlFlow: false,
    deprecated: false,
    experimental: false,
    inputs: [
      { id: 'prompt', type: 'STRING', optional: false, color: '#7BD88F', widget: 'string', forceInput: false },
      { id: 'max_turns', type: 'INT', optional: true, color: '#6E9BF5', widget: 'int', forceInput: false },
    ],
    outputs: [{ id: 'text', type: 'STRING', color: '#7BD88F', isList: false }],
    metadata: {},
  },
  'Art.ImageGen': {
    type: 'Art.ImageGen',
    displayName: 'Image Generation',
    category: 'art',
    description: '',
    isOutputNode: false,
    controlFlow: false,
    deprecated: false,
    experimental: false,
    inputs: [{ id: 'prompt', type: 'STRING', optional: false, color: '#7BD88F', widget: 'string', forceInput: false }],
    outputs: [{ id: 'image', type: 'IMAGE', color: '#64B5F6', isList: false }],
    metadata: {},
  },
};

describe('isWorkflowConnectionValid', () => {
  it('allows control-flow links from Start when types mismatch and target is not prompt feed', () => {
    const nodes = new Map([
      ['start', { id: 'start', data: { nodeType: 'StartNode' } }],
      ['agent', { id: 'agent', data: { nodeType: 'Agent.test' } }],
    ]);
    const conn = { source: 'start', target: 'agent', sourceHandle: 'inputs', targetHandle: 'max_turns' };
    expect(isWorkflowConnectionValid(conn, defs, (id) => nodes.get(id) as never)).toBe(true);
    expect(isControlFlowConnection(conn, defs, (id) => nodes.get(id) as never)).toBe(true);
    expect(isStartInputFeedConnection(conn, defs, (id) => nodes.get(id) as never)).toBe(false);
  });

  it('allows Start inputs bag into Agent prompt as a data link', () => {
    const nodes = new Map([
      ['start', { id: 'start', data: { nodeType: 'StartNode' } }],
      ['agent', { id: 'agent', data: { nodeType: 'Agent.test' } }],
    ]);
    const conn = { source: 'start', target: 'agent', sourceHandle: 'inputs', targetHandle: 'prompt' };
    expect(isStartInputFeedConnection(conn, defs, (id) => nodes.get(id) as never)).toBe(true);
    expect(isWorkflowConnectionValid(conn, defs, (id) => nodes.get(id) as never)).toBe(true);
    expect(isControlFlowConnection(conn, defs, (id) => nodes.get(id) as never)).toBe(false);
  });
});

describe('controlFlowEdgeData', () => {
  it('tags sequence edges for serialization', () => {
    expect(controlFlowEdgeData()).toEqual({
      kind: 'control',
      controlKind: 'next',
      color: '#94a3b8',
    });
  });
});
