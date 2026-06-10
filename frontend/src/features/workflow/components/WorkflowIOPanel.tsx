import { useTranslation } from 'react-i18next';
import { Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui';

import type { WorkflowInputSpec } from '../genui/inputsToGenUiTree';
import type { WorkflowOutputSpec } from '../genui/outputsToGenUiTree';

const INPUT_TYPES = ['string', 'number', 'integer', 'boolean', 'file', 'array', 'object'] as const;
const RENDERERS = ['auto', 'table', 'chart', 'card', 'markdown', 'image', 'json'] as const;

const FIELD_CLASS =
  'w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary-400';

export interface WorkflowIOPanelProps {
  inputs: WorkflowInputSpec[];
  outputs: WorkflowOutputSpec[];
  onChangeInputs: (next: WorkflowInputSpec[]) => void;
  onChangeOutputs: (next: WorkflowOutputSpec[]) => void;
}

/**
 * Authoring panel for `WorkflowDocument.inputs` / `outputs`: declared inputs
 * drive the generated GenUI run form; outputs carry render hints for the
 * structured result view.
 */
export function WorkflowIOPanel({
  inputs,
  outputs,
  onChangeInputs,
  onChangeOutputs,
}: WorkflowIOPanelProps) {
  const { t } = useTranslation();

  const patchInput = (i: number, patch: Partial<WorkflowInputSpec>) => {
    onChangeInputs(inputs.map((spec, idx) => (idx === i ? { ...spec, ...patch } : spec)));
  };
  const patchOutput = (i: number, patch: Partial<WorkflowOutputSpec>) => {
    onChangeOutputs(outputs.map((spec, idx) => (idx === i ? { ...spec, ...patch } : spec)));
  };

  return (
    <div className="flex min-h-0 flex-col gap-4 overflow-y-auto p-4">
      {/* ── Inputs ── */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t('ioPanel.inputs', 'Workflow inputs')}
          </h3>
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<Plus className="h-3 w-3" />}
            onClick={() =>
              onChangeInputs([
                ...inputs,
                { name: `input_${inputs.length + 1}`, type: 'string', required: false },
              ])
            }
          >
            {t('ioPanel.add', 'Add')}
          </Button>
        </div>
        {inputs.length === 0 && (
          <p className="text-xs text-muted-foreground">
            {t('ioPanel.noInputs', 'No declared inputs. The run form will be empty.')}
          </p>
        )}
        {inputs.map((spec, i) => (
          <div key={i} className="space-y-1.5 rounded-lg border border-border p-2">
            <div className="flex items-center gap-1.5">
              <input
                className={FIELD_CLASS}
                value={spec.name}
                placeholder={t('ioPanel.name', 'name')}
                onChange={(e) => patchInput(i, { name: e.target.value })}
              />
              <select
                className={FIELD_CLASS}
                value={String(spec.type ?? 'string')}
                onChange={(e) => patchInput(i, { type: e.target.value })}
              >
                {INPUT_TYPES.map((ty) => (
                  <option key={ty} value={ty}>
                    {ty}
                  </option>
                ))}
              </select>
              <button
                className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-red-500"
                onClick={() => onChangeInputs(inputs.filter((_, idx) => idx !== i))}
                title={t('ioPanel.remove', 'Remove')}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
            <input
              className={FIELD_CLASS}
              value={spec.description ?? ''}
              placeholder={t('ioPanel.description', 'Description')}
              onChange={(e) => patchInput(i, { description: e.target.value })}
            />
            <div className="flex items-center gap-2">
              <input
                className={FIELD_CLASS}
                value={spec.default !== undefined ? String(spec.default) : ''}
                placeholder={t('ioPanel.default', 'Default value')}
                onChange={(e) =>
                  patchInput(i, { default: e.target.value === '' ? undefined : e.target.value })
                }
              />
              <label className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={Boolean(spec.required)}
                  onChange={(e) => patchInput(i, { required: e.target.checked })}
                />
                {t('ioPanel.required', 'Required')}
              </label>
            </div>
            {String(spec.type) === 'string' && (
              <input
                className={FIELD_CLASS}
                value={Array.isArray(spec.choices) ? spec.choices.join(', ') : ''}
                placeholder={t('ioPanel.choices', 'Choices (comma-separated, optional)')}
                onChange={(e) => {
                  const parts = e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean);
                  patchInput(i, { choices: parts.length > 0 ? parts : undefined });
                }}
              />
            )}
          </div>
        ))}
      </section>

      {/* ── Outputs ── */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t('ioPanel.outputs', 'Workflow outputs')}
          </h3>
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<Plus className="h-3 w-3" />}
            onClick={() =>
              onChangeOutputs([...outputs, { name: `output_${outputs.length + 1}` }])
            }
          >
            {t('ioPanel.add', 'Add')}
          </Button>
        </div>
        {outputs.length === 0 && (
          <p className="text-xs text-muted-foreground">
            {t(
              'ioPanel.noOutputs',
              'No declared outputs. Results render from state variables automatically.',
            )}
          </p>
        )}
        {outputs.map((spec, i) => (
          <div key={i} className="space-y-1.5 rounded-lg border border-border p-2">
            <div className="flex items-center gap-1.5">
              <input
                className={FIELD_CLASS}
                value={spec.name}
                placeholder={t('ioPanel.name', 'name')}
                onChange={(e) => patchOutput(i, { name: e.target.value })}
              />
              <select
                className={FIELD_CLASS}
                value={spec.ui?.render ?? 'auto'}
                onChange={(e) => {
                  const render = e.target.value;
                  patchOutput(i, {
                    ui:
                      render === 'auto'
                        ? undefined
                        : { ...spec.ui, render: render as Exclude<typeof RENDERERS[number], 'auto'> },
                  });
                }}
              >
                {RENDERERS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
              <button
                className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-red-500"
                onClick={() => onChangeOutputs(outputs.filter((_, idx) => idx !== i))}
                title={t('ioPanel.remove', 'Remove')}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
            <input
              className={FIELD_CLASS}
              value={spec.description ?? ''}
              placeholder={t('ioPanel.description', 'Description')}
              onChange={(e) => patchOutput(i, { description: e.target.value })}
            />
          </div>
        ))}
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          {t(
            'ioPanel.outputsHint',
            'Output names map to workflow state variables; the renderer hint controls how each result is displayed.',
          )}
        </p>
      </section>
    </div>
  );
}
