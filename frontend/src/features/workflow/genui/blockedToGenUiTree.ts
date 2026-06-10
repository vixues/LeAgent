/**
 * Control-plane mapper: `execution_blocked` WS event → GenUI interaction tree.
 *
 * - Agent pause (`awaiting_user_input`): question + answer Textarea +
 *   resume button (`resume_workflow` → `{answer}`).
 * - Human review (`awaiting_review`): review summary + comments Textarea +
 *   Approve / Reject buttons (`resume_workflow` → `{approved, comments}`).
 *
 * If the blocking node attached its own `gen_ui` tree, that tree renders
 * verbatim instead of the generated form.
 */

import type { GenUiNode, GenUiTreeV1 } from '@/types/genUi';

export interface BlockedEventInfo {
  nodeId: string;
  /** Block tag, e.g. `awaiting_user_input` or `awaiting_review`. */
  tag: string;
  /** Raw `data.ui` payload from the `execution_blocked` event. */
  ui?: Record<string, unknown>;
}

let counter = 0;
function nid(prefix: string): string {
  counter += 1;
  return `${prefix}-blocked-${counter}`;
}

function asGenUiTree(value: unknown): GenUiTreeV1 | null {
  if (
    value &&
    typeof value === 'object' &&
    (value as { schemaVersion?: string }).schemaVersion === '1' &&
    (value as { root?: unknown }).root
  ) {
    return value as GenUiTreeV1;
  }
  return null;
}

export function blockedToGenUiTree(
  info: BlockedEventInfo,
  promptId: string,
  labels: {
    question?: string;
    answerPlaceholder?: string;
    resume?: string;
    approve?: string;
    reject?: string;
    commentsLabel?: string;
  } = {},
): GenUiTreeV1 {
  counter = 0;
  const ui = info.ui ?? {};

  // Node-supplied tree wins (validated server-side before emission).
  const custom = asGenUiTree(ui.gen_ui);
  if (custom) return custom;

  if (info.tag === 'awaiting_review') {
    const review = (ui.review ?? {}) as Record<string, unknown>;
    const prompt = typeof review.prompt === 'string' ? review.prompt : '';
    const reviewer = typeof review.reviewer === 'string' ? review.reviewer : '';
    const children: GenUiNode[] = [];
    if (prompt) {
      children.push({ nodeId: nid('md'), kind: 'Markdown', props: { content: prompt } });
    }
    if (reviewer) {
      children.push({
        nodeId: nid('rev'),
        kind: 'Text',
        props: { value: reviewer, size: 'xs', color: 'muted' },
      });
    }
    children.push({
      nodeId: nid('comments'),
      kind: 'Textarea',
      props: {
        name: 'comments',
        label: labels.commentsLabel ?? 'Comments',
        rows: 2,
      },
    });
    children.push({
      nodeId: nid('row'),
      kind: 'Row',
      props: { gap: 8, justify: 'end' },
      children: [
        {
          nodeId: nid('reject'),
          kind: 'InteractiveButton',
          props: {
            label: labels.reject ?? 'Reject',
            variant: 'danger',
            icon: 'x',
            action: {
              type: 'resume_workflow',
              payload: { promptId, values: { approved: false } },
            },
          },
        },
        {
          nodeId: nid('approve'),
          kind: 'InteractiveButton',
          props: {
            label: labels.approve ?? 'Approve',
            variant: 'primary',
            icon: 'check',
            action: {
              type: 'resume_workflow',
              payload: { promptId, values: { approved: true } },
            },
          },
        },
      ],
    });
    return {
      schemaVersion: '1',
      root: {
        nodeId: nid('form'),
        kind: 'Form',
        props: { formId: `review-${info.nodeId}` },
        children,
      },
    };
  }

  // Default: agent awaiting user input.
  const question = typeof ui.question === 'string' ? ui.question : labels.question ?? '';
  const children: GenUiNode[] = [];
  if (question) {
    children.push({ nodeId: nid('q'), kind: 'Markdown', props: { content: question } });
  }
  children.push({
    nodeId: nid('answer'),
    kind: 'Textarea',
    props: {
      name: 'answer',
      placeholder: labels.answerPlaceholder ?? 'Type your answer...',
      rows: 2,
      required: true,
    },
  });
  children.push({
    nodeId: nid('row'),
    kind: 'Row',
    props: { gap: 8, justify: 'end' },
    children: [
      {
        nodeId: nid('resume'),
        kind: 'InteractiveButton',
        props: {
          label: labels.resume ?? 'Resume',
          variant: 'primary',
          icon: 'send',
          action: {
            type: 'resume_workflow',
            payload: { promptId },
          },
        },
      },
    ],
  });
  return {
    schemaVersion: '1',
    root: {
      nodeId: nid('form'),
      kind: 'Form',
      props: { formId: `resume-${info.nodeId}` },
      children,
    },
  };
}
