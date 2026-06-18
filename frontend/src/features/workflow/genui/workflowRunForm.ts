/**
 * Helpers for collecting workflow run-panel form values from the GenUI form
 * store (keyed by flow id) and merging them with declared input defaults.
 */

import { useGenUiFormsStore } from '@/stores/genUiForms';

import { coerceFormValues, type WorkflowInputSpec } from './inputsToGenUiTree';

const INPUT_TEMPLATE = /\$\{input\.([a-zA-Z_][a-zA-Z0-9_]*)\}/g;

/** Scan node widget values for ``${input.name}`` references. */
export function inferWorkflowInputsFromValues(
  nodeValues: Iterable<Record<string, unknown>>,
): WorkflowInputSpec[] {
  const names = new Set<string>();
  for (const values of nodeValues) {
    for (const v of Object.values(values)) {
      if (typeof v !== 'string') continue;
      for (const m of v.matchAll(INPUT_TEMPLATE)) {
        const name = m[1];
        if (name) names.add(name);
      }
    }
  }
  return [...names].sort().map((name) => ({
    name,
    type: 'string',
    multiline: name === 'prompt' || name.includes('prompt'),
    label: name === 'prompt' ? 'Prompt' : name.replace(/_/g, ' '),
    required: false,
  }));
}

export function workflowInputsFormKey(
  flowId: string,
  ctx?: { sessionId?: string; messageId?: string },
): string {
  return `${ctx?.sessionId ?? 'scope'}::${ctx?.messageId ?? 'root'}::workflow-inputs-${flowId}`;
}

/** Declared defaults from ``WorkflowDocument.inputs`` specs. */
export function inputDefaults(
  inputs: WorkflowInputSpec[] | null | undefined,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const spec of inputs ?? []) {
    if (!spec?.name) continue;
    if (spec.default !== undefined) out[spec.name] = spec.default;
  }
  return out;
}

/**
 * Merge live form edits (if the run panel was mounted) with schema defaults,
 * then coerce to the declared input types for the run API.
 */
export function collectWorkflowRunInputValues(
  flowId: string,
  inputs: WorkflowInputSpec[] | null | undefined,
  ctx?: { sessionId?: string; messageId?: string },
): Record<string, unknown> {
  const formKey = workflowInputsFormKey(flowId, ctx);
  const fromForm = useGenUiFormsStore.getState().getValues(formKey);
  const merged = { ...inputDefaults(inputs), ...fromForm };
  return coerceFormValues(merged, inputs);
}
