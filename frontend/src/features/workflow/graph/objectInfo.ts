/**
 * Parse the backend `/object_info` payload into a typed `NodeDefinition`
 * registry the React Flow editor renders from.
 *
 * The backend emits one entry per registered workflow node (builtin, tool,
 * agent, and domain-model nodes) with ComfyUI-shaped input/output metadata
 * plus editor rendering hints (`color`, `widget`, `output_colors`). This
 * module is framework-agnostic and unit-tested independently of React.
 */

import { socketColor, DEFAULT_SOCKET_COLORS } from './socketTypes';

/** Widget kinds the editor knows how to render inline on a node. */
export type WidgetKind =
  | 'string'
  | 'int'
  | 'float'
  | 'toggle'
  | 'combo'
  | 'file'
  | 'datetime'
  | '';

export interface InputSlot {
  id: string;
  /** Wire type used for link compatibility (e.g. STRING, IMAGE, COMBO). */
  type: string;
  optional: boolean;
  color: string;
  widget: WidgetKind;
  /** For FILE inputs: accepted mime/extensions (e.g. "image/*,.pdf"). */
  accept?: string;
  /** For COMBO inputs: the available choices. */
  choices?: string[];
  default?: unknown;
  multiline?: boolean;
  min?: number;
  max?: number;
  step?: number;
  tooltip?: string;
  /** Whether the input must be linked (no inline widget). */
  forceInput: boolean;
}

export interface OutputSlot {
  id: string;
  type: string;
  color: string;
  isList: boolean;
  tooltip?: string;
}

export interface NodeDefinition {
  /** Backend node id, e.g. `Tool.image_generate`, `Agent.coding_agent`. */
  type: string;
  displayName: string;
  category: string;
  description: string;
  isOutputNode: boolean;
  /** Participates in control-flow sequencing (Start/End/Gate…). */
  controlFlow: boolean;
  deprecated: boolean;
  experimental: boolean;
  inputs: InputSlot[];
  outputs: OutputSlot[];
  metadata: Record<string, unknown>;
}

export interface ObjectInfo {
  definitions: Record<string, NodeDefinition>;
  socketColors: Record<string, string>;
  /** Definitions grouped by their top-level category for the palette. */
  categories: Record<string, NodeDefinition[]>;
}

type RawInputEntry = [unknown, Record<string, unknown>];
interface RawNode {
  name?: string;
  display_name?: string;
  category?: string;
  description?: string;
  output_node?: boolean;
  deprecated?: boolean;
  experimental?: boolean;
  input?: {
    required?: Record<string, RawInputEntry>;
    optional?: Record<string, RawInputEntry>;
    hidden?: Record<string, string>;
  };
  input_order?: string[];
  output?: string[];
  output_name?: string[];
  output_is_list?: boolean[];
  output_colors?: string[];
  output_tooltips?: string[];
  control_flow?: boolean;
  metadata?: Record<string, unknown>;
}

export interface ObjectInfoResponse {
  nodes: Record<string, RawNode>;
  socket_colors?: Record<string, string>;
}

function widgetKind(raw: unknown): WidgetKind {
  const allowed: WidgetKind[] = [
    'string',
    'int',
    'float',
    'toggle',
    'combo',
    'file',
    'datetime',
  ];
  return typeof raw === 'string' && (allowed as string[]).includes(raw)
    ? (raw as WidgetKind)
    : '';
}

function parseInput(
  id: string,
  entry: RawInputEntry,
  optional: boolean,
  legend: Record<string, string>,
): InputSlot {
  const [rawType, rawOptions] = entry;
  const options = (rawOptions ?? {}) as Record<string, unknown>;
  // COMBO inputs serialize their wire `type` as the list of choices.
  const isCombo = Array.isArray(rawType);
  const wireType = isCombo ? 'COMBO' : String(rawType ?? '*');
  const color =
    typeof options.color === 'string' ? options.color : socketColor(wireType, legend);
  return {
    id,
    type: wireType,
    optional,
    color,
    widget: widgetKind(options.widget) || (isCombo ? 'combo' : ''),
    accept: typeof options.accept === 'string' ? options.accept : undefined,
    choices: isCombo ? (rawType as string[]).map(String) : undefined,
    default: options.default,
    multiline: options.multiline === true,
    min: typeof options.min === 'number' ? options.min : undefined,
    max: typeof options.max === 'number' ? options.max : undefined,
    step: typeof options.step === 'number' ? options.step : undefined,
    tooltip: typeof options.tooltip === 'string' ? options.tooltip : undefined,
    forceInput: options.forceInput === true,
  };
}

function parseNode(
  type: string,
  raw: RawNode,
  legend: Record<string, string>,
): NodeDefinition {
  const inputDefs = raw.input ?? {};
  const order = raw.input_order ?? [];
  const requiredEntries = inputDefs.required ?? {};
  const optionalEntries = inputDefs.optional ?? {};

  const byId = new Map<string, InputSlot>();
  for (const [id, entry] of Object.entries(requiredEntries)) {
    byId.set(id, parseInput(id, entry, false, legend));
  }
  for (const [id, entry] of Object.entries(optionalEntries)) {
    byId.set(id, parseInput(id, entry, true, legend));
  }

  // Honour input_order, then append any inputs not referenced by it.
  const inputs: InputSlot[] = [];
  for (const id of order) {
    const slot = byId.get(id);
    if (slot) {
      inputs.push(slot);
      byId.delete(id);
    }
  }
  for (const slot of byId.values()) inputs.push(slot);

  const outTypes = raw.output ?? [];
  const outNames = raw.output_name ?? [];
  const outColors = raw.output_colors ?? [];
  const outIsList = raw.output_is_list ?? [];
  const outTooltips = raw.output_tooltips ?? [];
  const outputs: OutputSlot[] = outTypes.map((t, i) => ({
    id: outNames[i] || `out${i}`,
    type: String(t),
    color: outColors[i] || socketColor(String(t), legend),
    isList: Boolean(outIsList[i]),
    tooltip: outTooltips[i],
  }));

  return {
    type,
    displayName: raw.display_name || raw.name || type,
    category: raw.category || 'workflow',
    description: raw.description || '',
    isOutputNode: Boolean(raw.output_node),
    controlFlow: Boolean(raw.control_flow),
    deprecated: Boolean(raw.deprecated),
    experimental: Boolean(raw.experimental),
    inputs,
    outputs,
    metadata: raw.metadata ?? {},
  };
}

/** Parse a raw `/object_info` response into the editor's node registry. */
export function parseObjectInfo(resp: ObjectInfoResponse): ObjectInfo {
  const legend = { ...DEFAULT_SOCKET_COLORS, ...(resp.socket_colors ?? {}) };
  const definitions: Record<string, NodeDefinition> = {};
  for (const [type, raw] of Object.entries(resp.nodes ?? {})) {
    definitions[type] = parseNode(type, raw, legend);
  }

  const categories: Record<string, NodeDefinition[]> = {};
  for (const def of Object.values(definitions)) {
    const top = def.category.split('/')[0] || 'workflow';
    (categories[top] ??= []).push(def);
  }
  for (const list of Object.values(categories)) {
    list.sort((a, b) => a.displayName.localeCompare(b.displayName));
  }

  return { definitions, socketColors: legend, categories };
}
