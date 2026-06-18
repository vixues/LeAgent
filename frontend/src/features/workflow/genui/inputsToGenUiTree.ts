/**
 * Deterministic mapper: `WorkflowDocument.inputs` → GenUI `Form` tree.
 *
 * The generated form is rendered by the shared `GenUiTreeView`; its submit
 * button dispatches a `run_workflow` action whose values are collected from
 * the form scope. No LLM involved — the tree is derived 1:1 from the
 * declared workflow input specs.
 */

import type { GenUiNode, GenUiTreeV1 } from '@/types/genUi';

/** One entry of `WorkflowDocument.inputs` (loose dict on the backend). */
export interface WorkflowInputSpec {
  name: string;
  type?: string;
  required?: boolean;
  default?: unknown;
  /** Human-readable label shown on the run form (defaults to ``name``). */
  label?: string;
  description?: string;
  /** Enum-like restriction (editor-authored). */
  choices?: unknown[];
  multiline?: boolean;
  rows?: number;
  min?: number;
  max?: number;
  step?: number;
  [key: string]: unknown;
}

let counter = 0;
function nid(prefix: string): string {
  counter += 1;
  return `${prefix}-${counter}`;
}

function fieldFor(spec: WorkflowInputSpec): GenUiNode {
  const displayLabel = spec.label?.trim() || spec.name;
  const base = {
    label: displayLabel,
    name: spec.name,
    required: Boolean(spec.required),
    description: spec.description,
  };
  const type = String(spec.type ?? 'string').toLowerCase();

  if (Array.isArray(spec.choices) && spec.choices.length > 0) {
    return {
      nodeId: nid('field'),
      kind: 'Select',
      props: {
        ...base,
        options: spec.choices.map((c) => String(c)),
        value: spec.default !== undefined ? String(spec.default) : undefined,
      },
    };
  }

  switch (type) {
    case 'number':
    case 'float':
      return {
        nodeId: nid('field'),
        kind: 'NumberInput',
        props: { ...base, value: spec.default, min: spec.min, max: spec.max, step: spec.step },
      };
    case 'integer':
    case 'int':
      return {
        nodeId: nid('field'),
        kind: 'NumberInput',
        props: {
          ...base,
          value: spec.default,
          min: spec.min,
          max: spec.max,
          step: spec.step ?? 1,
          integer: true,
        },
      };
    case 'boolean':
    case 'bool':
      return {
        nodeId: nid('field'),
        kind: 'Switch',
        props: { ...base, value: spec.default ?? false },
      };
    case 'file':
      return {
        nodeId: nid('field'),
        kind: 'FileInput',
        props: { ...base, value: spec.default },
      };
    case 'array':
    case 'object':
    case 'json':
      return {
        nodeId: nid('field'),
        kind: 'Textarea',
        props: {
          ...base,
          value:
            spec.default !== undefined ? JSON.stringify(spec.default, null, 2) : undefined,
          placeholder: type === 'array' ? '[ ... ]' : '{ ... }',
          rows: 4,
          description: spec.description ?? 'JSON',
        },
      };
    case 'string':
    default:
      if (spec.multiline) {
        return {
          nodeId: nid('field'),
          kind: 'Textarea',
          props: {
            ...base,
            value: spec.default,
            rows: typeof spec.rows === 'number' ? spec.rows : 5,
          },
        };
      }
      return {
        nodeId: nid('field'),
        kind: 'Input',
        props: { ...base, value: spec.default, type: 'text' },
      };
  }
}

export interface InputsFormOptions {
  flowId: string;
  /** Form heading (defaults to none — host surface provides chrome). */
  title?: string;
  description?: string;
  submitLabel?: string;
}

/** Build the runnable GenUI input form for a workflow. */
export function inputsToGenUiTree(
  inputs: WorkflowInputSpec[] | undefined | null,
  opts: InputsFormOptions,
): GenUiTreeV1 | null {
  counter = 0;
  const specs = (inputs ?? []).filter(
    (s): s is WorkflowInputSpec => Boolean(s) && typeof s === 'object' && Boolean(s.name),
  );
  if (specs.length === 0) return null;

  const children: GenUiNode[] = specs.map(fieldFor);
  children.push({
    nodeId: nid('submit'),
    kind: 'InteractiveButton',
    props: {
      label: opts.submitLabel ?? 'Run',
      icon: 'play',
      variant: 'primary',
      action: {
        type: 'run_workflow',
        payload: { flowId: opts.flowId },
      },
    },
  });

  return {
    schemaVersion: '1',
    root: {
      nodeId: nid('form'),
      kind: 'Form',
      props: {
        formId: `workflow-inputs-${opts.flowId}`,
        title: opts.title,
        description: opts.description,
      },
      children,
    },
  };
}

/**
 * Coerce collected form values back to the declared input types
 * (numbers stay numbers; JSON text fields are parsed).
 */
export function coerceFormValues(
  values: Record<string, unknown>,
  inputs: WorkflowInputSpec[] | undefined | null,
): Record<string, unknown> {
  const byName = new Map<string, WorkflowInputSpec>();
  for (const spec of inputs ?? []) {
    if (spec && typeof spec === 'object' && spec.name) byName.set(spec.name, spec);
  }
  const out: Record<string, unknown> = {};
  for (const [key, raw] of Object.entries(values)) {
    const spec = byName.get(key);
    const type = String(spec?.type ?? '').toLowerCase();
    if ((type === 'array' || type === 'object' || type === 'json') && typeof raw === 'string') {
      try {
        out[key] = raw.trim() === '' ? undefined : JSON.parse(raw);
      } catch {
        out[key] = raw;
      }
      continue;
    }
    if ((type === 'integer' || type === 'int') && typeof raw === 'string' && raw !== '') {
      const n = parseInt(raw, 10);
      out[key] = Number.isNaN(n) ? raw : n;
      continue;
    }
    if ((type === 'number' || type === 'float') && typeof raw === 'string' && raw !== '') {
      const n = parseFloat(raw);
      out[key] = Number.isNaN(n) ? raw : n;
      continue;
    }
    out[key] = raw;
  }
  // Drop undefined so backend defaults still apply.
  for (const key of Object.keys(out)) {
    if (out[key] === undefined) delete out[key];
  }
  return out;
}

/** Validation: returns missing required input names given collected values. */
export function missingRequiredInputs(
  values: Record<string, unknown>,
  inputs: WorkflowInputSpec[] | undefined | null,
): string[] {
  const missing: string[] = [];
  for (const spec of inputs ?? []) {
    if (!spec || typeof spec !== 'object' || !spec.name || !spec.required) continue;
    if (spec.default !== undefined) continue;
    const v = values[spec.name];
    if (v === undefined || v === null || v === '') missing.push(spec.name);
  }
  return missing;
}
