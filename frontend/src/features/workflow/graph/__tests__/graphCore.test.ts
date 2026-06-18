import { describe, expect, it } from 'vitest';

import {
  parseObjectInfo,
  type NodeDefinition,
  type ObjectInfoResponse,
} from '../objectInfo';
import {
  fromStoredDocument,
  finalizeExecutableGraph,
  toCanonicalDocument,
  type EditorEdge,
  type EditorNode,
} from '../serialization';
import {
  DEFAULT_SOCKET_COLOR,
  DEFAULT_SOCKET_COLORS,
  socketColor,
  typesCompatible,
} from '../socketTypes';

// ---------------------------------------------------------------------------
// socketTypes
// ---------------------------------------------------------------------------

describe('typesCompatible', () => {
  it('matches identical types', () => {
    expect(typesCompatible('STRING', 'STRING')).toBe(true);
  });

  it('rejects unrelated types', () => {
    expect(typesCompatible('IMAGE', 'STRING')).toBe(false);
  });

  it('wildcard matches everything on either side', () => {
    expect(typesCompatible('*', 'IMAGE')).toBe(true);
    expect(typesCompatible('STRING', '*')).toBe(true);
  });

  it('multi-type descriptors match on intersection', () => {
    expect(typesCompatible('STRING,INT', 'INT')).toBe(true);
    expect(typesCompatible('IMAGE', 'IMAGE,VIDEO')).toBe(true);
    expect(typesCompatible('STRING,INT', 'IMAGE,VIDEO')).toBe(false);
  });
});

describe('socketColor', () => {
  it('resolves known types from the default legend', () => {
    expect(socketColor('STRING')).toBe(DEFAULT_SOCKET_COLORS.STRING);
  });

  it('prefers a runtime legend over defaults', () => {
    expect(socketColor('STRING', { STRING: '#123456' })).toBe('#123456');
  });

  it('uses the first known member for multi-type descriptors', () => {
    expect(socketColor('IMAGE,VIDEO')).toBe(DEFAULT_SOCKET_COLORS.IMAGE);
  });

  it('falls back for unknown types', () => {
    expect(socketColor('CUSTOM_THING')).toBe(DEFAULT_SOCKET_COLOR);
  });
});

// ---------------------------------------------------------------------------
// objectInfo parsing
// ---------------------------------------------------------------------------

const RAW: ObjectInfoResponse = {
  socket_colors: { STRING: '#7BD88F', INT: '#6E9BF5' },
  nodes: {
    StartNode: {
      name: 'StartNode',
      display_name: 'Start',
      category: 'workflow/control',
      control_flow: true,
      input: { required: {}, optional: {} },
      output: ['OBJECT'],
      output_name: ['inputs'],
    },
    EndNode: {
      name: 'EndNode',
      display_name: 'End',
      category: 'workflow/control',
      output_node: true,
      control_flow: true,
      input: { required: {}, optional: {} },
      output: ['OBJECT'],
      output_name: ['outputs'],
    },
    'Art.ImageGen': {
      name: 'Art.ImageGen',
      display_name: 'Image Generation',
      category: 'art/generate',
      control_flow: false,
      input: {
        required: {
          prompt: ['STRING', { multiline: true, widget: 'string' }],
        },
        optional: {},
      },
      output: ['IMAGE'],
      output_name: ['image'],
    },
    'Tool.echo': {
      name: 'Tool.echo',
      display_name: 'Echo',
      category: 'tools/text',
      description: 'Echo a string',
      input: {
        required: {
          text: ['STRING', { multiline: true, widget: 'string', color: '#7BD88F' }],
          count: ['INT', { default: 1, min: 0, max: 10, widget: 'int' }],
        },
        optional: {
          mode: [['fast', 'slow'], { default: 'fast' }],
        },
      },
      input_order: ['text', 'count', 'mode'],
      output: ['STRING'],
      output_name: ['result'],
      output_is_list: [false],
      output_colors: ['#7BD88F'],
    },
  },
};

describe('parseObjectInfo', () => {
  it('parses control_flow on boundary nodes', () => {
    const info = parseObjectInfo(RAW);
    expect(info.definitions.StartNode?.controlFlow).toBe(true);
    expect(info.definitions.EndNode?.controlFlow).toBe(true);
    expect(info.definitions['Art.ImageGen']?.controlFlow).toBe(false);
  });

  it('parses definitions with ordered inputs and widget hints', () => {
    const info = parseObjectInfo(RAW);
    const def = info.definitions['Tool.echo']!;
    expect(def.displayName).toBe('Echo');
    expect(def.inputs.map((i) => i.id)).toEqual(['text', 'count', 'mode']);

    const text = def.inputs[0]!;
    expect(text.widget).toBe('string');
    expect(text.multiline).toBe(true);
    expect(text.optional).toBe(false);

    const count = def.inputs[1]!;
    expect(count.widget).toBe('int');
    expect(count.min).toBe(0);
    expect(count.max).toBe(10);
    expect(count.default).toBe(1);
  });

  it('treats array wire types as COMBO with choices', () => {
    const info = parseObjectInfo(RAW);
    const mode = info.definitions['Tool.echo']!.inputs[2]!;
    expect(mode.type).toBe('COMBO');
    expect(mode.widget).toBe('combo');
    expect(mode.choices).toEqual(['fast', 'slow']);
    expect(mode.optional).toBe(true);
  });

  it('parses outputs with colors', () => {
    const info = parseObjectInfo(RAW);
    const out = info.definitions['Tool.echo']!.outputs[0]!;
    expect(out.id).toBe('result');
    expect(out.type).toBe('STRING');
    expect(out.color).toBe('#7BD88F');
  });

  it('groups definitions by top-level category', () => {
    const info = parseObjectInfo(RAW);
    expect(info.categories.tools?.map((d) => d.type)).toEqual(['Tool.echo']);
  });
});

// ---------------------------------------------------------------------------
// Model.<task>.<provider> domain-model nodes (self-hosted diffusion shape)
// ---------------------------------------------------------------------------

const MODEL_RAW: ObjectInfoResponse = {
  socket_colors: { STRING: '#7BD88F', FLOAT: '#9AD8E0', COMBO: '#C7A9F2' },
  nodes: {
    'Model.image_gen.local': {
      name: 'Model.image_gen.local',
      display_name: 'Image Generation (Local Diffusion)',
      category: 'models/image_gen',
      input: {
        required: {
          prompt: ['STRING', { multiline: true, widget: 'string' }],
        },
        optional: {
          model: [
            ['dreamshaperXL.safetensors', 'stabilityai/stable-diffusion-xl-base-1.0'],
            { default: 'dreamshaperXL.safetensors' },
          ],
          lora: [['none', 'detail.safetensors'], { default: 'none' }],
          cfg_scale: [
            'FLOAT',
            { default: 7, min: 0, max: 30, widget: 'float' },
          ],
        },
      },
      input_order: ['prompt', 'model', 'lora', 'cfg_scale'],
      output: ['STRING', 'STRING', 'STRING', 'OBJECT', 'BOOLEAN'],
      output_name: ['text', 'data_b64', 'mime', 'result', 'success'],
      output_is_list: [false, false, false, false, false],
      metadata: { domain_task: 'image_gen', domain_provider: 'local' },
    },
  },
};

describe('parseObjectInfo: Model.* domain-model nodes', () => {
  it('renders COMBO model/LoRA choices as combo widgets', () => {
    const info = parseObjectInfo(MODEL_RAW);
    const def = info.definitions['Model.image_gen.local']!;
    expect(def.category).toBe('models/image_gen');

    const model = def.inputs[1]!;
    expect(model.type).toBe('COMBO');
    expect(model.widget).toBe('combo');
    expect(model.choices).toEqual([
      'dreamshaperXL.safetensors',
      'stabilityai/stable-diffusion-xl-base-1.0',
    ]);
    expect(model.default).toBe('dreamshaperXL.safetensors');

    const lora = def.inputs[2]!;
    expect(lora.choices).toEqual(['none', 'detail.safetensors']);
  });

  it('renders FLOAT params with slider bounds', () => {
    const info = parseObjectInfo(MODEL_RAW);
    const cfg = info.definitions['Model.image_gen.local']!.inputs[3]!;
    expect(cfg.widget).toBe('float');
    expect(cfg.min).toBe(0);
    expect(cfg.max).toBe(30);
    expect(cfg.color).toBe('#9AD8E0');
  });

  it('exposes the uniform 5-slot output envelope', () => {
    const info = parseObjectInfo(MODEL_RAW);
    const def = info.definitions['Model.image_gen.local']!;
    expect(def.outputs.map((o) => o.id)).toEqual([
      'text',
      'data_b64',
      'mime',
      'result',
      'success',
    ]);
    expect(def.metadata.domain_task).toBe('image_gen');
    expect(info.categories.models?.map((d) => d.type)).toEqual([
      'Model.image_gen.local',
    ]);
  });
});

// ---------------------------------------------------------------------------
// serialization round-trip
// ---------------------------------------------------------------------------

function editorFixture(): { nodes: EditorNode[]; edges: EditorEdge[] } {
  const nodes: EditorNode[] = [
    {
      id: 'a',
      type: 'workflow',
      position: { x: 10, y: 20 },
      data: {
        nodeType: 'Tool.echo',
        label: 'Echo A',
        category: 'tools/text',
        values: { text: 'hello', count: 2 },
      },
    },
    {
      id: 'b',
      type: 'workflow',
      position: { x: 400, y: 20 },
      data: {
        nodeType: 'Tool.echo',
        label: 'Echo B',
        category: 'tools/text',
        values: { count: 1 },
      },
    },
  ];
  const edges: EditorEdge[] = [
    {
      id: 'e1',
      source: 'a',
      sourceHandle: 'result',
      target: 'b',
      targetHandle: 'text',
      type: 'workflow',
    },
  ];
  return { nodes, edges };
}

describe('toCanonicalDocument', () => {
  it('emits canonical nodes with literal values and link refs', () => {
    const info = parseObjectInfo(RAW);
    const { nodes, edges } = editorFixture();
    const doc = toCanonicalDocument({
      id: 'flow-1',
      name: 'Test Flow',
      nodes,
      edges,
      definitions: info.definitions,
    });

    expect(new Set(Object.keys(doc.nodes))).toEqual(new Set(['a', 'b', 'end']));
    expect(doc.nodes.a!.class_type).toBe('Tool.echo');
    expect(doc.nodes.a!.inputs).toEqual({ text: 'hello', count: 2 });
    // b.text is link-driven: [upstream_node_id, output_slot_index]
    expect(doc.nodes.b!.inputs.text).toEqual(['a', 0]);
    expect(doc.nodes.b!.inputs.count).toBe(1);
  });

  it('picks the node with no incoming edges as start', () => {
    const info = parseObjectInfo(RAW);
    const { nodes, edges } = editorFixture();
    const doc = toCanonicalDocument({
      id: '',
      name: 'x',
      nodes,
      edges,
      definitions: info.definitions,
    });
    expect(doc.control.start).toBe('a');
    expect(doc.nodes.b?.control?.next).toBe('end');
  });

  it('stores the editor layout in the ui block', () => {
    const info = parseObjectInfo(RAW);
    const { nodes, edges } = editorFixture();
    const doc = toCanonicalDocument({
      id: '',
      name: 'x',
      nodes,
      edges,
      viewport: { x: 1, y: 2, zoom: 1.5 },
      definitions: info.definitions,
    });
    expect(doc.ui.nodes).toHaveLength(2);
    expect(doc.ui.viewport).toEqual({ x: 1, y: 2, zoom: 1.5 });
  });

  it('preserves per-node control blocks from control-flow edges on save', () => {
    const info = parseObjectInfo(RAW);
    const stored = {
      nodes: {
        start: {
          class_type: 'StartNode',
          inputs: {},
          control: { next: 'work' },
        },
        work: {
          class_type: 'Tool.echo',
          inputs: { text: 'hello' },
          control: { next: 'end' },
        },
        end: { class_type: 'EndNode', inputs: {} },
      },
      control: { start: 'start', edges: [] },
    };
    const restored = fromStoredDocument(stored, info.definitions);
    const doc = toCanonicalDocument({
      id: 'flow-ctl',
      name: 'Control round-trip',
      nodes: restored.nodes,
      edges: restored.edges,
      definitions: info.definitions,
    });
    expect(doc.nodes.start?.control).toEqual({ next: 'work' });
    expect(doc.nodes.work?.control).toEqual({ next: 'end' });
  });

  it('does not serialise control-flow edges as data input links (CHAR-2D self-correction)', () => {
    const definitions: Record<string, NodeDefinition> = {
      'Art.ImageGen': {
        type: 'Art.ImageGen',
        displayName: 'Image Generation',
        category: 'art',
        description: '',
        isOutputNode: false,
        deprecated: false,
        experimental: false,
        inputs: [
          { id: 'prompt', type: 'STRING', optional: false, color: '#7BD88F', widget: 'string', forceInput: false },
          { id: 'width', type: 'INT', optional: true, color: '#6E9BF5', widget: 'int', forceInput: false },
        ],
        outputs: [{ id: 'image', type: 'IMAGE', color: '#F5A623', isList: false }],
        metadata: {},
      },
      'Art.QualityCritic': {
        type: 'Art.QualityCritic',
        displayName: 'Quality Critic',
        category: 'art',
        description: '',
        isOutputNode: false,
        deprecated: false,
        experimental: false,
        inputs: [
          { id: 'asset', type: 'IMAGE', optional: true, color: '#F5A623', widget: 'string', forceInput: false },
        ],
        outputs: [
          { id: 'score', type: 'FLOAT', color: '#6E9BF5', isList: false },
          { id: 'passed', type: 'BOOLEAN', color: '#6E9BF5', isList: false },
          { id: 'asset', type: 'IMAGE', color: '#F5A623', isList: false },
        ],
        metadata: {},
      },
      QualityGateNode: {
        type: 'QualityGateNode',
        displayName: 'Quality Gate',
        category: 'art',
        description: '',
        isOutputNode: false,
        deprecated: false,
        experimental: false,
        inputs: [
          { id: 'asset', type: 'IMAGE', optional: true, color: '#F5A623', widget: 'string', forceInput: false },
          { id: 'score', type: 'FLOAT', optional: true, color: '#6E9BF5', widget: 'float', forceInput: false },
        ],
        outputs: [
          { id: 'score', type: 'FLOAT', color: '#6E9BF5', isList: false },
          { id: 'passed', type: 'BOOLEAN', color: '#6E9BF5', isList: false },
          { id: 'asset', type: 'IMAGE', color: '#F5A623', isList: false },
        ],
        metadata: {},
      },
      IterativeRefineNode: {
        type: 'IterativeRefineNode',
        displayName: 'Iterative Refine',
        category: 'art',
        description: '',
        isOutputNode: false,
        deprecated: false,
        experimental: false,
        inputs: [
          { id: 'max_iterations', type: 'INT', optional: true, color: '#6E9BF5', widget: 'int', forceInput: false },
          { id: 'feedback', type: 'STRING', optional: true, color: '#7BD88F', widget: 'string', forceInput: false },
        ],
        outputs: [{ id: 'feedback', type: 'STRING', color: '#7BD88F', isList: false }],
        metadata: {},
      },
      'Art.Upscale': {
        type: 'Art.Upscale',
        displayName: 'Upscale',
        category: 'art',
        description: '',
        isOutputNode: false,
        deprecated: false,
        experimental: false,
        inputs: [
          { id: 'image', type: 'IMAGE', optional: false, color: '#F5A623', widget: 'string', forceInput: false },
          { id: 'prompt', type: 'STRING', optional: true, color: '#7BD88F', widget: 'string', forceInput: false },
        ],
        outputs: [{ id: 'image', type: 'IMAGE', color: '#F5A623', isList: false }],
        metadata: {},
      },
    };

    const stored = {
      nodes: {
        concept: {
          class_type: 'Art.ImageGen',
          inputs: {
            prompt: '${input.prompt}',
            width: 1024,
            provider: 'offline',
          },
          control: { next: 'critic' },
        },
        critic: {
          class_type: 'Art.QualityCritic',
          inputs: { asset: ['concept', 0] },
          control: { next: 'gate' },
        },
        gate: {
          class_type: 'QualityGateNode',
          inputs: { asset: ['critic', 2], score: ['critic', 0], threshold: 0.7 },
          control: { conditions: [{ then_node: 'upscale' }], else_node: 'refine' },
        },
        refine: {
          class_type: 'IterativeRefineNode',
          inputs: { max_iterations: 2, feedback: 'improve silhouette' },
          control: { retry_node: 'concept', exhausted_node: 'upscale' },
        },
        upscale: {
          class_type: 'Art.Upscale',
          inputs: { image: ['gate', 2], prompt: 'sharp detail', provider: 'offline' },
        },
      },
      control: { start: 'concept', edges: [] },
    };

    const restored = fromStoredDocument(stored, definitions);
    const doc = toCanonicalDocument({
      id: 'char-2d',
      name: 'CHAR 2D',
      nodes: restored.nodes,
      edges: restored.edges,
      definitions,
    });

    expect(doc.nodes.concept?.inputs.prompt).toBe('${input.prompt}');
    expect(doc.nodes.refine?.inputs.max_iterations).toBe(2);
    expect(doc.nodes.upscale?.inputs.image).toEqual(['gate', 2]);
    expect(doc.nodes.gate?.control).toEqual({
      conditions: [{ then_node: 'upscale' }],
      else_node: 'refine',
    });
    expect(doc.nodes.refine?.control).toEqual({
      retry_node: 'concept',
      exhausted_node: 'upscale',
    });
  });
});

describe('toCanonicalDocument: UI-layer reroutes and groups', () => {
  function rerouteFixture(): { nodes: EditorNode[]; edges: EditorEdge[] } {
    const { nodes } = editorFixture();
    const reroute: EditorNode = {
      id: 'r1',
      type: 'reroute',
      position: { x: 200, y: 20 },
      data: { nodeType: '__reroute__', label: '', category: 'ui' },
    };
    // a.result → r1 → b.text
    const edges: EditorEdge[] = [
      {
        id: 'e-a-r1',
        source: 'a',
        sourceHandle: 'result',
        target: 'r1',
        targetHandle: 'in',
        type: 'workflow',
      },
      {
        id: 'e-r1-b',
        source: 'r1',
        sourceHandle: 'out',
        target: 'b',
        targetHandle: 'text',
        type: 'workflow',
      },
    ];
    return { nodes: [...nodes, reroute], edges };
  }

  it('flattens reroute chains to the true upstream producer', () => {
    const info = parseObjectInfo(RAW);
    const { nodes, edges } = rerouteFixture();
    const doc = toCanonicalDocument({
      id: '',
      name: 'x',
      nodes,
      edges,
      definitions: info.definitions,
    });
    // The reroute never reaches the executable graph...
    expect(new Set(Object.keys(doc.nodes))).toEqual(new Set(['a', 'b', 'end']));
    // ...but the link it carried is preserved end-to-end.
    expect(doc.nodes.b!.inputs.text).toEqual(['a', 0]);
    expect(doc.control.edges).toEqual([
      { source: 'a', target: 'b', source_slot: 0, target_slot: 0 },
    ]);
    // The ui block keeps the reroute for visual round-trips.
    expect(doc.ui.nodes.map((n) => n.id)).toContain('r1');
  });

  it('flattens multi-hop reroute chains', () => {
    const info = parseObjectInfo(RAW);
    const { nodes, edges } = rerouteFixture();
    const r2: EditorNode = {
      id: 'r2',
      type: 'reroute',
      position: { x: 300, y: 20 },
      data: { nodeType: '__reroute__', label: '', category: 'ui' },
    };
    // a → r1 → r2 → b
    const chained: EditorEdge[] = [
      edges[0]!,
      { ...edges[1]!, id: 'e-r1-r2', target: 'r2', targetHandle: 'in' },
      {
        id: 'e-r2-b',
        source: 'r2',
        sourceHandle: 'out',
        target: 'b',
        targetHandle: 'text',
        type: 'workflow',
      },
    ];
    const doc = toCanonicalDocument({
      id: '',
      name: 'x',
      nodes: [...nodes, r2],
      edges: chained,
      definitions: info.definitions,
    });
    expect(doc.nodes.b!.inputs.text).toEqual(['a', 0]);
    expect(doc.control.edges).toHaveLength(1);
  });

  it('drops dangling reroutes without emitting broken links', () => {
    const info = parseObjectInfo(RAW);
    const { nodes } = rerouteFixture();
    // Only r1 → b exists; r1 has no incoming edge.
    const edges: EditorEdge[] = [
      {
        id: 'e-r1-b',
        source: 'r1',
        sourceHandle: 'out',
        target: 'b',
        targetHandle: 'text',
        type: 'workflow',
      },
    ];
    const doc = toCanonicalDocument({
      id: '',
      name: 'x',
      nodes,
      edges,
      definitions: info.definitions,
    });
    expect(doc.nodes.b!.inputs.text).toBeUndefined();
    expect(doc.control.edges).toEqual([]);
  });

  it('excludes group frames from the executable graph', () => {
    const info = parseObjectInfo(RAW);
    const { nodes, edges } = editorFixture();
    const group: EditorNode = {
      id: 'g1',
      type: 'group',
      position: { x: 0, y: 0 },
      style: { width: 600, height: 300 },
      data: { nodeType: '__group__', label: 'Group', category: 'ui' },
    };
    const doc = toCanonicalDocument({
      id: '',
      name: 'x',
      nodes: [group, ...nodes],
      edges,
      definitions: info.definitions,
    });
    expect(new Set(Object.keys(doc.nodes))).toEqual(new Set(['a', 'b', 'end']));
    expect(doc.ui.nodes.map((n) => n.id)).toContain('g1');
  });

  it('serializes node modes into meta and restores them', () => {
    const info = parseObjectInfo(RAW);
    const { nodes, edges } = editorFixture();
    nodes[0]!.data.mode = 'mute';
    nodes[1]!.data.mode = 'bypass';
    const doc = toCanonicalDocument({
      id: '',
      name: 'x',
      nodes,
      edges,
      definitions: info.definitions,
    });
    expect(doc.nodes.a!.meta.mode).toBe('mute');
    expect(doc.nodes.b!.meta.mode).toBe('bypass');

    // Canonical-only restore carries the mode back into editor data.
    const restored = fromStoredDocument(
      { nodes: doc.nodes, control: doc.control },
      info.definitions,
    );
    expect(restored.nodes.find((n) => n.id === 'a')!.data.mode).toBe('mute');
    expect(restored.nodes.find((n) => n.id === 'b')!.data.mode).toBe('bypass');
  });

  it('carries declared workflow I/O through serialize/restore', () => {
    const info = parseObjectInfo(RAW);
    const { nodes, edges } = editorFixture();
    const inputs = [{ name: 'query', type: 'string', required: true }];
    const outputs = [{ name: 'result', ui: { render: 'table' } }];
    const doc = toCanonicalDocument({
      id: '',
      name: 'x',
      nodes,
      edges,
      definitions: info.definitions,
      inputs,
      outputs,
    });
    expect(doc.inputs).toEqual(inputs);
    expect(doc.outputs).toEqual(outputs);
    const restored = fromStoredDocument(JSON.parse(JSON.stringify(doc)), info.definitions);
    expect(restored.inputs).toEqual(inputs);
    expect(restored.outputs).toEqual(outputs);
  });
});

describe('fromStoredDocument', () => {
  it('round-trips via the ui block', () => {
    const info = parseObjectInfo(RAW);
    const { nodes, edges } = editorFixture();
    const doc = toCanonicalDocument({
      id: '',
      name: 'x',
      nodes,
      edges,
      definitions: info.definitions,
    });
    const restored = fromStoredDocument(JSON.parse(JSON.stringify(doc)), info.definitions);
    expect(restored.nodes.map((n) => n.id)).toEqual(['a', 'b']);
    expect(restored.edges.some((e) => e.source === 'a' && e.target === 'b')).toBe(true);
    expect(restored.nodes[0]!.data.values).toEqual({ text: 'hello', count: 2 });
  });

  it('rebuilds editor nodes/edges from a canonical-only document', () => {
    const info = parseObjectInfo(RAW);
    const canonicalOnly = {
      nodes: {
        a: {
          class_type: 'Tool.echo',
          inputs: { text: 'hi' },
          meta: { position: { x: 5, y: 6 }, title: 'A' },
        },
        b: {
          class_type: 'Tool.echo',
          inputs: { text: ['a', 0] },
          meta: { position: { x: 300, y: 6 } },
        },
      },
      control: { start: 'a', edges: [] },
    };
    const restored = fromStoredDocument(canonicalOnly, info.definitions);
    expect(restored.nodes).toHaveLength(2);
    expect(restored.nodes[0]!.position).toEqual({ x: 5, y: 6 });
    expect(restored.edges).toHaveLength(1);
    expect(restored.edges[0]).toMatchObject({
      source: 'a',
      target: 'b',
      sourceHandle: 'result',
      targetHandle: 'text',
    });
  });

  it('rebuilds control-flow edges from control.next when no data links exist', () => {
    const info = parseObjectInfo(RAW);
    const linearTemplate = {
      nodes: {
        start: {
          class_type: 'StartNode',
          inputs: {},
          control: { next: 'work' },
        },
        work: {
          class_type: 'Tool.echo',
          inputs: { text: 'hello' },
          control: { next: 'end' },
        },
        end: {
          class_type: 'EndNode',
          inputs: {},
        },
      },
      control: { start: 'start', edges: [] },
    };
    const restored = fromStoredDocument(linearTemplate, info.definitions);
    expect(restored.edges).toContainEqual(
      expect.objectContaining({ source: 'start', target: 'work' }),
    );
    expect(restored.edges).toContainEqual(
      expect.objectContaining({ source: 'work', target: 'end' }),
    );
  });

  it('rebuilds typed nodes when the ui block is preview-shaped (templates)', () => {
    const info = parseObjectInfo(RAW);
    // Mirrors what `apply_template` stores: canonical nodes + a sibling `ui`
    // block authored by the backend layout helper (generic, ChatWorkflowMiniNode
    // shape — no `data.nodeType`). The typed editor must ignore the generic
    // projection and rebuild `workflow` nodes, reusing the laid-out positions.
    const stored = {
      nodes: {
        a: {
          class_type: 'Tool.echo',
          inputs: { text: 'hi' },
          meta: { name: 'Concept' },
        },
        b: {
          class_type: 'Tool.echo',
          inputs: { text: ['a', 0] },
          meta: { name: 'Refine' },
        },
      },
      control: { start: 'a', edges: [] },
      ui: {
        nodes: [
          { id: 'a', type: 'generic', position: { x: 800, y: 80 }, data: { label: 'Concept', icon: 'tool_call' } },
          { id: 'b', type: 'generic', position: { x: 1520, y: 80 }, data: { label: 'Refine', icon: 'tool_call' } },
        ],
        edges: [{ id: 'e-a-b-next', source: 'a', target: 'b', type: 'default' }],
      },
    };
    const restored = fromStoredDocument(stored, info.definitions);
    // Typed editor nodes, not bare React Flow defaults.
    expect(restored.nodes.every((n) => n.type === 'workflow')).toBe(true);
    expect(restored.nodes.map((n) => n.data.nodeType)).toEqual(['Tool.echo', 'Tool.echo']);
    // The friendly `meta.name` becomes the label.
    expect(restored.nodes.find((n) => n.id === 'a')!.data.label).toBe('Concept');
    // The backend-computed layout positions are reused verbatim.
    expect(restored.nodes.find((n) => n.id === 'b')!.position).toEqual({ x: 1520, y: 80 });
    // Data-link edges are reconstructed from canonical inputs.
    expect(restored.edges).toContainEqual(
      expect.objectContaining({ source: 'a', target: 'b', targetHandle: 'text' }),
    );
  });

  it('keeps unknown class_types as placeholder nodes with config intact', () => {
    const info = parseObjectInfo(RAW);
    const canonicalOnly = {
      nodes: {
        ghost: {
          class_type: 'Tool.removed_pack',
          inputs: { secret: 'kept', linked: ['a', 0] },
          meta: { position: { x: 1, y: 2 } },
        },
        a: {
          class_type: 'Tool.echo',
          inputs: { text: 'hi' },
          meta: { position: { x: 0, y: 0 } },
        },
      },
      control: { start: 'a', edges: [] },
    };
    const restored = fromStoredDocument(canonicalOnly, info.definitions);
    const ghost = restored.nodes.find((n) => n.id === 'ghost')!;
    // Missing types are not dropped — the editor renders the flagged
    // placeholder and the stored literal config survives a round-trip.
    expect(ghost.data.nodeType).toBe('Tool.removed_pack');
    expect(ghost.data.values).toEqual({ secret: 'kept' });
    // The stored link is preserved as an edge too.
    expect(restored.edges).toContainEqual(
      expect.objectContaining({ source: 'a', target: 'ghost' }),
    );
  });

  it('round-trips canvas asset nodes through canonical LoadImage', () => {
    const info = parseObjectInfo(RAW);
    const assetId = 'asset-1';
    const nodes: EditorNode[] = [
      {
        id: assetId,
        type: 'canvas-asset',
        position: { x: 10, y: 20 },
        style: { width: 180, height: 120 },
        data: {
          assetKind: 'image',
          fileId: 'file-uuid',
          fileName: 'demo.png',
          previewUrl: '/api/v1/files/file-uuid/preview',
          label: 'demo.png',
        },
      } as EditorNode,
      {
        id: 'b',
        type: 'workflow',
        position: { x: 300, y: 20 },
        data: {
          nodeType: 'Tool.echo',
          label: 'Echo',
          category: 'tool',
          values: {},
        },
      },
    ];
    const edges: EditorEdge[] = [
      {
        id: 'e1',
        source: assetId,
        target: 'b',
        sourceHandle: 'image',
        targetHandle: 'text',
        type: 'workflow',
      },
    ];
    const doc = toCanonicalDocument({
      id: 'wf',
      name: 'asset-test',
      nodes,
      edges,
      definitions: info.definitions,
    });
    expect(doc.nodes[assetId]?.class_type).toBe('LoadImage');
    const restored = fromStoredDocument(doc, info.definitions);
    const asset = restored.nodes.find((n) => n.id === assetId);
    expect(asset?.type).toBe('canvas-asset');
    expect(restored.edges.some((e) => e.source === assetId && e.target === 'b')).toBe(true);
  });

  it('returns empty graph for unparseable payloads', () => {
    const empty = { nodes: [], edges: [], inputs: [], outputs: [] };
    expect(fromStoredDocument('not json', {})).toEqual(empty);
    expect(fromStoredDocument(null, {})).toEqual(empty);
  });
});

describe('finalizeExecutableGraph', () => {
  it('injects start/end and chains a lone ImageGen node', () => {
    const finalized = finalizeExecutableGraph(
      {
        image_1: {
          class_type: 'Art.ImageGen',
          inputs: { prompt: 'a cat', provider: 'offline' },
          meta: { title: 'Gen' },
        },
      },
      { edges: [] },
      ['image_1'],
    );
    expect(finalized.nodes.start?.class_type).toBe('StartNode');
    expect(finalized.nodes.end?.class_type).toBe('EndNode');
    expect(finalized.nodes.start?.control?.next).toBe('image_1');
    expect(finalized.nodes.image_1?.control?.next).toBe('end');
    expect(finalized.control.start).toBe('start');
    expect(finalized.control.end).toBe('end');
  });

  it('preserves explicit control.next from editor edges on save', () => {
    const info = parseObjectInfo(RAW);
    const nodes: EditorNode[] = [
      {
        id: 'start',
        type: 'workflow',
        position: { x: 0, y: 0 },
        data: { nodeType: 'StartNode', label: 'Start', category: 'workflow' },
      },
      {
        id: 'img',
        type: 'workflow',
        position: { x: 200, y: 0 },
        data: {
          nodeType: 'Art.ImageGen',
          label: 'Gen',
          category: 'art',
          values: { prompt: 'hello' },
        },
      },
      {
        id: 'end',
        type: 'workflow',
        position: { x: 400, y: 0 },
        data: { nodeType: 'EndNode', label: 'End', category: 'workflow' },
      },
    ];
    const edges: EditorEdge[] = [
      {
        id: 'e-start-img-next',
        source: 'start',
        target: 'img',
        type: 'workflow',
        data: { kind: 'control', controlKind: 'next', color: '#94a3b8' },
      },
      {
        id: 'e-img-end-next',
        source: 'img',
        target: 'end',
        type: 'workflow',
        data: { kind: 'control', controlKind: 'next', color: '#94a3b8' },
      },
    ];
    const doc = toCanonicalDocument({
      id: 'wf',
      name: 'chain',
      nodes,
      edges,
      definitions: info.definitions,
    });
    expect(doc.nodes.start?.control?.next).toBe('img');
    expect(doc.nodes.img?.control?.next).toBe('end');
    expect(doc.control.end).toBe('end');
  });
});
