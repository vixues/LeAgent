import { describe, expect, it } from 'vitest';

import type { GenUiNode } from '@/types/genUi';

import {
  coerceFormValues,
  inputsToGenUiTree,
  missingRequiredInputs,
  type WorkflowInputSpec,
} from '../inputsToGenUiTree';

function fields(treeChildren: GenUiNode[] | undefined): GenUiNode[] {
  // All children except the trailing submit button.
  return (treeChildren ?? []).slice(0, -1);
}

describe('inputsToGenUiTree', () => {
  it('wraps fields in a Form with a run_workflow submit button', () => {
    const tree = inputsToGenUiTree(
      [{ name: 'query', type: 'string', required: true }],
      { flowId: 'f1', submitLabel: 'Go' },
    )!;
    expect(tree.root.kind).toBe('Form');
    expect(tree.root.props?.formId).toBe('workflow-inputs-f1');

    const submit = tree.root.children!.at(-1)!;
    expect(submit.kind).toBe('InteractiveButton');
    expect(submit.props?.label).toBe('Go');
    expect(submit.props?.action).toEqual({
      type: 'run_workflow',
      payload: { flowId: 'f1' },
    });
  });

  it('maps declared types to the matching field kinds', () => {
    const specs: WorkflowInputSpec[] = [
      { name: 's', type: 'string' },
      { name: 'ml', type: 'string', multiline: true },
      { name: 'n', type: 'number', min: 0, max: 10, step: 0.5 },
      { name: 'i', type: 'integer' },
      { name: 'b', type: 'boolean', default: true },
      { name: 'f', type: 'file' },
      { name: 'j', type: 'object', default: { a: 1 } },
      { name: 'arr', type: 'array' },
    ];
    const tree = inputsToGenUiTree(specs, { flowId: 'f1' })!;
    const kinds = fields(tree.root.children).map((c) => c.kind);
    expect(kinds).toEqual([
      'Input',
      'Textarea',
      'NumberInput',
      'NumberInput',
      'Switch',
      'FileInput',
      'Textarea',
      'Textarea',
    ]);

    const [, , num, int, sw, , json] = fields(tree.root.children);
    expect(num!.props).toMatchObject({ min: 0, max: 10, step: 0.5 });
    expect(int!.props).toMatchObject({ integer: true, step: 1 });
    expect(sw!.props?.value).toBe(true);
    expect(json!.props?.value).toBe(JSON.stringify({ a: 1 }, null, 2));
  });

  it('renders enum-like choices as Select regardless of type', () => {
    const tree = inputsToGenUiTree(
      [{ name: 'mode', type: 'string', choices: ['fast', 'slow'], default: 'fast' }],
      { flowId: 'f1' },
    )!;
    const field = fields(tree.root.children)[0]!;
    expect(field.kind).toBe('Select');
    expect(field.props?.options).toEqual(['fast', 'slow']);
    expect(field.props?.value).toBe('fast');
  });

  it('returns null when there are no valid input specs', () => {
    expect(inputsToGenUiTree([], { flowId: 'f1' })).toBeNull();
    expect(inputsToGenUiTree(null, { flowId: 'f1' })).toBeNull();
    expect(
      inputsToGenUiTree([null, {}] as unknown as WorkflowInputSpec[], { flowId: 'f1' }),
    ).toBeNull();
  });

  it('uses label on the run form when provided', () => {
    const tree = inputsToGenUiTree(
      [{ name: 'prompt', type: 'string', label: 'Prompt', multiline: true, rows: 6 }],
      { flowId: 'f1' },
    );
    const field = fields(tree!.root.children)[0]!;
    expect(field.props?.label).toBe('Prompt');
    expect(field.props?.rows).toBe(6);
  });

  it('skips malformed specs and still emits the submit button', () => {
    const tree = inputsToGenUiTree(
      [null, {}, { name: 'ok' }] as unknown as WorkflowInputSpec[],
      { flowId: 'f1' },
    )!;
    expect(tree.root.children).toHaveLength(2); // ok field + submit
  });
});

describe('coerceFormValues', () => {
  const specs: WorkflowInputSpec[] = [
    { name: 'count', type: 'integer' },
    { name: 'ratio', type: 'number' },
    { name: 'payload', type: 'json' },
    { name: 'note', type: 'string' },
  ];

  it('coerces numeric strings back to numbers', () => {
    const out = coerceFormValues({ count: '5', ratio: '0.5' }, specs);
    expect(out).toEqual({ count: 5, ratio: 0.5 });
  });

  it('parses JSON text fields and keeps invalid JSON as text', () => {
    expect(coerceFormValues({ payload: '{"a": 1}' }, specs)).toEqual({
      payload: { a: 1 },
    });
    expect(coerceFormValues({ payload: 'not json' }, specs)).toEqual({
      payload: 'not json',
    });
  });

  it('drops empty JSON fields so backend defaults apply', () => {
    expect(coerceFormValues({ payload: '  ' }, specs)).toEqual({});
  });

  it('passes through untyped and string values unchanged', () => {
    expect(coerceFormValues({ note: 'hi', extra: 1 }, specs)).toEqual({
      note: 'hi',
      extra: 1,
    });
  });
});

describe('missingRequiredInputs', () => {
  it('reports required fields without values or defaults', () => {
    const specs: WorkflowInputSpec[] = [
      { name: 'a', required: true },
      { name: 'b', required: true, default: 'x' },
      { name: 'c', required: false },
    ];
    expect(missingRequiredInputs({}, specs)).toEqual(['a']);
    expect(missingRequiredInputs({ a: '' }, specs)).toEqual(['a']);
    expect(missingRequiredInputs({ a: 'v' }, specs)).toEqual([]);
  });
});
