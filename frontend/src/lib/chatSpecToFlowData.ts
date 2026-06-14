import type { ChatWorkflowSpecModel } from '@/types/chat';

/**
 * Build a bare canonical workflow document from a chat workflow spec so the
 * shared mini-graph preview can layout nodes and control-flow edges.
 */
export function chatSpecToFlowData(spec: ChatWorkflowSpecModel): Record<string, unknown> {
  const steps = spec.steps ?? [];
  if (steps.length === 0) {
    return {
      id: 'chat-spec-preview',
      name: spec.title,
      nodes: {
        start: {
          class_type: 'StartNode',
          inputs: {},
          meta: { name: 'Start' },
          control: { next: 'end' },
        },
        end: {
          class_type: 'EndNode',
          inputs: {},
          meta: { name: 'End' },
          control: {},
        },
      },
      control: { start: 'start', end: 'end', edges: [] },
    };
  }

  const nodes: Record<string, unknown> = {
    start: {
      class_type: 'StartNode',
      inputs: {},
      meta: { name: 'Start' },
      control: { next: steps[0]!.id },
    },
  };

  steps.forEach((step, index) => {
    const next = index < steps.length - 1 ? steps[index + 1]!.id : 'end';
    nodes[step.id] = {
      class_type: 'ToolCallNode',
      inputs: {
        tool: step.action.tool_id,
        params: step.action.arguments ?? {},
      },
      meta: {
        name: step.label,
        description: step.hint ?? '',
      },
      control: { next },
    };
  });

  nodes.end = {
    class_type: 'EndNode',
    inputs: {},
    meta: { name: 'End' },
    control: {},
  };

  return {
    id: 'chat-spec-preview',
    name: spec.title,
    description: spec.summary ?? '',
    nodes,
    control: { start: 'start', end: 'end', edges: [] },
  };
}
