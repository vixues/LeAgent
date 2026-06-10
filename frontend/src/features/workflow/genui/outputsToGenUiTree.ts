/**
 * Deterministic mapper: resolved workflow outputs → GenUI component tree.
 *
 * Shapes map by structure (array-of-objects → Table, object → KeyValueList,
 * scalar → Stat, text → Markdown), with optional per-output `ui` hints from
 * the workflow definition (`render: table|chart|card|markdown|image|json`).
 * Nodes may also emit a full GenUI tree via `NodeOutput.ui.gen_ui` — those
 * pass through untouched (already validated server-side).
 */

import type { GenUiNode, GenUiTreeV1 } from '@/types/genUi';

/** One entry of `WorkflowDocument.outputs` (loose dict on the backend). */
export interface WorkflowOutputSpec {
  name: string;
  description?: string;
  /** Optional renderer hint authored in the workflow I/O panel. */
  ui?: {
    render?: 'table' | 'chart' | 'card' | 'markdown' | 'image' | 'json';
    options?: Record<string, unknown>;
  };
  [key: string]: unknown;
}

let counter = 0;
function nid(prefix: string): string {
  counter += 1;
  return `${prefix}-out-${counter}`;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === 'object' && !Array.isArray(v);
}

function cellText(v: unknown): string {
  if (v === null || v === undefined) return '';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function tableFor(rows: Record<string, unknown>[]): GenUiNode {
  const headers = Array.from(
    rows.reduce((set, row) => {
      for (const k of Object.keys(row)) set.add(k);
      return set;
    }, new Set<string>()),
  );
  return {
    nodeId: nid('table'),
    kind: 'Table',
    props: { headers, striped: true, compact: true },
    children: rows.slice(0, 200).map((row) => ({
      nodeId: nid('tr'),
      kind: 'TableRow',
      children: headers.map((h) => ({
        nodeId: nid('td'),
        kind: 'TableCell',
        props: { value: cellText(row[h]) },
      })),
    })),
  };
}

function chartFor(name: string, value: unknown, options?: Record<string, unknown>): GenUiNode {
  let categories: string[] = [];
  let series: Array<{ name: string; values: number[] }> = [];

  if (isPlainObject(value) && Array.isArray(value.categories) && Array.isArray(value.series)) {
    categories = (value.categories as unknown[]).map(String);
    series = (value.series as unknown[]).filter(isPlainObject).map((sr) => ({
      name: String(sr.name ?? name),
      values: Array.isArray(sr.values) ? (sr.values as unknown[]).map(Number) : [],
    }));
  } else if (Array.isArray(value) && value.every((v) => typeof v === 'number')) {
    categories = value.map((_, i) => String(i + 1));
    series = [{ name, values: value as number[] }];
  } else if (Array.isArray(value) && value.every(isPlainObject)) {
    // Array of objects: first string-ish key = category, numeric keys = series.
    const rows = value as Record<string, unknown>[];
    const keys = Object.keys(rows[0] ?? {});
    const catKey = keys.find((k) => typeof rows[0]?.[k] === 'string') ?? keys[0];
    const numKeys = keys.filter((k) => k !== catKey && typeof rows[0]?.[k] === 'number');
    categories = rows.map((r) => cellText(catKey ? r[catKey] : ''));
    series = numKeys.map((k) => ({ name: k, values: rows.map((r) => Number(r[k] ?? 0)) }));
  }

  return {
    nodeId: nid('chart'),
    kind: 'Chart',
    props: {
      chart: (options?.chart as string) ?? 'bar',
      title: (options?.title as string) ?? name,
      categories,
      series,
      ...(options ?? {}),
    },
  };
}

function autoNodeFor(name: string, value: unknown): GenUiNode {
  if (Array.isArray(value)) {
    if (value.length > 0 && value.every(isPlainObject)) {
      return tableFor(value as Record<string, unknown>[]);
    }
    return {
      nodeId: nid('list'),
      kind: 'List',
      children: value.slice(0, 100).map((item) => ({
        nodeId: nid('li'),
        kind: 'ListItem',
        props: { value: cellText(item) },
      })),
    };
  }
  if (isPlainObject(value)) {
    return {
      nodeId: nid('kv'),
      kind: 'KeyValueList',
      props: {
        columns: 1,
        items: Object.entries(value).map(([label, v]) => ({ label, value: cellText(v) })),
      },
    };
  }
  if (typeof value === 'number') {
    return { nodeId: nid('stat'), kind: 'Stat', props: { label: name, value: String(value) } };
  }
  if (typeof value === 'boolean') {
    return {
      nodeId: nid('badge'),
      kind: 'Badge',
      props: { value: value ? 'true' : 'false', variant: value ? 'success' : 'default' },
    };
  }
  return {
    nodeId: nid('md'),
    kind: 'Markdown',
    props: { content: cellText(value) },
  };
}

function nodeFor(name: string, value: unknown, spec?: WorkflowOutputSpec): GenUiNode {
  const render = spec?.ui?.render;
  const options = spec?.ui?.options;
  switch (render) {
    case 'table':
      if (Array.isArray(value) && value.every(isPlainObject)) {
        return tableFor(value as Record<string, unknown>[]);
      }
      return autoNodeFor(name, value);
    case 'chart':
      return chartFor(name, value, options);
    case 'markdown':
      return { nodeId: nid('md'), kind: 'Markdown', props: { content: cellText(value) } };
    case 'image':
      return {
        nodeId: nid('img'),
        kind: 'Image',
        props: { src: cellText(value), alt: name, rounded: true, ...(options ?? {}) },
      };
    case 'card':
      return {
        nodeId: nid('card'),
        kind: 'DataCard',
        props: {
          title: name,
          value: typeof value === 'object' ? '' : cellText(value),
          description: spec?.description,
          ...(options ?? {}),
        },
        children: typeof value === 'object' ? [autoNodeFor(name, value)] : undefined,
      };
    case 'json':
      return {
        nodeId: nid('json'),
        kind: 'CodeBlock',
        props: { code: JSON.stringify(value, null, 2), language: 'json', title: name },
      };
    default:
      return autoNodeFor(name, value);
  }
}

/**
 * Build the GenUI result tree from resolved workflow outputs.
 *
 * `genUiTrees` are explicit `NodeOutput.ui.gen_ui` trees collected from
 * `executed` events — they render first, verbatim.
 */
export function outputsToGenUiTree(
  outputs: Record<string, unknown> | undefined | null,
  specs?: WorkflowOutputSpec[] | null,
  genUiTrees?: GenUiTreeV1[],
): GenUiTreeV1 | null {
  counter = 0;
  const byName = new Map<string, WorkflowOutputSpec>();
  for (const spec of specs ?? []) {
    if (spec && typeof spec === 'object' && spec.name) byName.set(spec.name, spec);
  }

  const children: GenUiNode[] = [];

  for (const tree of genUiTrees ?? []) {
    if (tree?.root) children.push(tree.root);
  }

  const entries = Object.entries(outputs ?? {});
  for (const [name, value] of entries) {
    const spec = byName.get(name);
    const rendered = nodeFor(name, value, spec);
    if (entries.length > 1 || spec?.description) {
      children.push({
        nodeId: nid('section'),
        kind: 'Stack',
        props: { gap: 4 },
        children: [
          {
            nodeId: nid('heading'),
            kind: 'SectionHeader',
            props: { title: name, description: spec?.description },
          },
          rendered,
        ],
      });
    } else {
      children.push(rendered);
    }
  }

  if (children.length === 0) return null;

  return {
    schemaVersion: '1',
    root: {
      nodeId: nid('root'),
      kind: 'Stack',
      props: { gap: 12 },
      children,
    },
  };
}
