import { beforeEach, describe, expect, it } from 'vitest';

import { useGenUiFormsStore } from '@/stores/genUiForms';

import type { WorkflowInputSpec } from '../inputsToGenUiTree';
import {
  collectWorkflowRunInputValues,
  inferWorkflowInputsFromValues,
  inputDefaults,
  workflowInputsFormKey,
} from '../workflowRunForm';

describe('workflowRunForm', () => {
  const specs: WorkflowInputSpec[] = [
    { name: 'prompt', type: 'string', default: 'default prompt', multiline: true },
    { name: 'style', type: 'string', default: 'realistic', choices: ['realistic', 'pixel_art'] },
  ];

  beforeEach(() => {
    useGenUiFormsStore.setState({ values: {} });
  });

  it('builds a stable form key per flow', () => {
    expect(workflowInputsFormKey('flow-1')).toBe('scope::root::workflow-inputs-flow-1');
  });

  it('returns schema defaults when the run form was never mounted', () => {
    expect(collectWorkflowRunInputValues('f1', specs)).toEqual({
      prompt: 'default prompt',
      style: 'realistic',
    });
  });

  it('merges live form edits over defaults', () => {
    const key = workflowInputsFormKey('f1');
    useGenUiFormsStore.getState().setField(key, 'prompt', 'user typed this');
    expect(collectWorkflowRunInputValues('f1', specs)).toEqual({
      prompt: 'user typed this',
      style: 'realistic',
    });
  });

  it('extracts defaults from specs', () => {
    expect(inputDefaults(specs)).toEqual({
      prompt: 'default prompt',
      style: 'realistic',
    });
  });

  it('infers input specs from node template literals', () => {
    const inferred = inferWorkflowInputsFromValues([
      { prompt: '${input.prompt}. Style: ${input.style}' },
    ]);
    expect(inferred.map((s) => s.name)).toEqual(['prompt', 'style']);
    expect(inferred[0]?.multiline).toBe(true);
  });
});
