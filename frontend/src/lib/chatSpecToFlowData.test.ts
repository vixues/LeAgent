import { describe, expect, it } from 'vitest';

import { extractWorkflowEdges } from '@/lib/workflowLayout';
import { parseStoredFlowDataForChatPreview } from '@/lib/parseFlowDataFromApi';
import { chatSpecToFlowData } from './chatSpecToFlowData';

describe('chatSpecToFlowData', () => {
  it('builds a linear chain with control-flow edges', () => {
    const flow = chatSpecToFlowData({
      version: 1,
      title: 'Demo',
      steps: [
        {
          id: 'step_a',
          label: 'Read file',
          action: { kind: 'tool', tool_id: 'pdf_reader', arguments: {} },
        },
        {
          id: 'step_b',
          label: 'Parse JSON',
          action: { kind: 'tool', tool_id: 'json_parser', arguments: {} },
        },
      ],
    });

    const nodes = flow.nodes as Record<string, { control?: { next?: string } }>;
    expect(nodes.start?.control?.next).toBe('step_a');
    expect(nodes.step_a?.control?.next).toBe('step_b');
    expect(nodes.step_b?.control?.next).toBe('end');

    const engineNodes = Object.entries(nodes).map(([id, spec]) => ({ id, ...spec }));
    const edges = extractWorkflowEdges(engineNodes);
    expect(edges.length).toBe(3);

    const preview = parseStoredFlowDataForChatPreview(flow);
    expect(preview.nodes.length).toBe(4);
    expect(preview.edges.length).toBe(3);
  });
});
