import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import { useReactFlow } from '@xyflow/react';

import { useNodeDefinition } from '../graph/registryContext';
import type { EditorNode } from '../graph/serialization';
import { NodeWidget } from './NodeWidget';

interface NodeInspectorProps {
  node: EditorNode;
  onClose: () => void;
}

/**
 * Right-hand config panel for the selected node. Shows every input (including
 * link-only ones) with its widget, plus output slots. This is also the agent
 * config surface: `Agent.<name>` nodes expose prompt / max_turns /
 * allowed_tools / project_path here with full-width editors.
 */
export function NodeInspector({ node, onClose }: NodeInspectorProps) {
  const { t } = useTranslation('workflows');
  const def = useNodeDefinition(node.data.nodeType);
  const { updateNodeData } = useReactFlow();

  const setValue = (slotId: string, value: unknown) => {
    updateNodeData(node.id, {
      values: { ...(node.data.values ?? {}), [slotId]: value },
    });
  };

  return (
    <aside className="flex w-80 flex-col border-l border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-foreground">
            {node.data.label || def?.displayName || node.data.nodeType}
          </h3>
          <p className="truncate text-[10px] text-muted-foreground">
            {node.data.nodeType}
          </p>
        </div>
        <button
          className="rounded p-1 text-muted-foreground hover:bg-accent"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-3">
        <div>
          <label className="mb-1 block text-[11px] font-medium text-muted-foreground">
            {t('flowEditor.nodeLabel', 'Label')}
          </label>
          <input
            className="w-full rounded border border-border bg-background px-2 py-1 text-xs outline-none"
            value={node.data.label}
            onChange={(e) => updateNodeData(node.id, { label: e.target.value })}
          />
        </div>

        {def?.description && (
          <p className="text-xs text-muted-foreground">{def.description}</p>
        )}

        {def && def.inputs.length > 0 && (
          <div>
            <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              {t('flowEditor.inputsHeading', 'Inputs')}
            </h4>
            <div className="space-y-3">
              {def.inputs.map((slot) => (
                <div key={slot.id}>
                  <div className="mb-1 flex items-center gap-1.5">
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-full"
                      style={{ background: slot.color }}
                      title={slot.type}
                    />
                    <label className="text-[11px] font-medium text-foreground">
                      {slot.id}
                    </label>
                    {slot.optional && (
                      <span className="text-[9px] text-muted-foreground">optional</span>
                    )}
                  </div>
                  {slot.widget ? (
                    <NodeWidget
                      slot={slot}
                      value={node.data.values?.[slot.id] ?? slot.default}
                      onChange={(v) => setValue(slot.id, v)}
                    />
                  ) : (
                    <p className="text-[10px] italic text-muted-foreground">
                      {t('flowEditor.linkOnlyInput', 'Set by linking an upstream node')}
                    </p>
                  )}
                  {slot.tooltip && (
                    <p className="mt-0.5 text-[10px] text-muted-foreground">
                      {slot.tooltip}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {def && def.outputs.length > 0 && (
          <div>
            <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              {t('flowEditor.outputsHeading', 'Outputs')}
            </h4>
            <ul className="space-y-1">
              {def.outputs.map((slot) => (
                <li key={slot.id} className="flex items-center gap-1.5 text-xs">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ background: slot.color }}
                  />
                  <span className="text-foreground">{slot.id}</span>
                  <span className="text-[10px] text-muted-foreground">{slot.type}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </aside>
  );
}
