import { describe, expect, it } from 'vitest';

import {
  parseObjectInfo,
  type ObjectInfoResponse,
} from '../objectInfo';
import {
  fromStoredDocument,
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

    expect(Object.keys(doc.nodes)).toEqual(['a', 'b']);
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
    expect(Object.keys(doc.nodes)).toEqual(['a', 'b']);
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
    expect(Object.keys(doc.nodes)).toEqual(['a', 'b']);
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
    expect(restored.edges).toHaveLength(1);
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
