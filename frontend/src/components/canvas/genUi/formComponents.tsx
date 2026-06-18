/**
 * Interactive GenUi form scope + field renderers.
 *
 * A `Form` node establishes a value scope (backed by `useGenUiFormsStore`).
 * Named field children become controlled inputs; buttons inside the form
 * collect the values via `useGenUiFormExtras()` and attach them to
 * `submit_form` / `run_workflow` / `resume_workflow` actions.
 *
 * Fields without an enclosing Form (or without a `name` prop) keep the
 * legacy display-only behaviour so existing chat trees render unchanged.
 */

import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';

import { cn } from '@/lib/utils';
import { useGenUiFormsStore } from '@/stores/genUiForms';
import type { GenUiNode } from '@/types/genUi';
import type { GenUiRenderContextValue } from '@/components/canvas/genUi/GenUiRenderContext';

const s = (v: unknown): string => (typeof v === 'string' ? v : v != null ? String(v) : '');

interface GenUiFormScope {
  formKey: string;
  formId: string;
}

const GenUiFormContext = createContext<GenUiFormScope | null>(null);

/** Read the enclosing Form scope (if any). */
export function useGenUiFormScope(): GenUiFormScope | null {
  return useContext(GenUiFormContext);
}

/** Extras a form-aware button merges into its action context. */
export function useGenUiFormExtras(): {
  formValues?: Record<string, unknown>;
  formId?: string;
} {
  const scope = useContext(GenUiFormContext);
  const values = useGenUiFormsStore((st) => (scope ? st.values[scope.formKey] : undefined));
  if (!scope) return {};
  return { formValues: values ?? {}, formId: scope.formId };
}

function formKeyFor(ctx: GenUiRenderContextValue, formId: string): string {
  return `${ctx.sessionId ?? 'scope'}::${ctx.messageId ?? 'root'}::${formId}`;
}

/** Snapshot form values at click time (avoids stale closures on submit buttons). */
export function formExtrasAtClick(scope: GenUiFormScope | null): {
  formValues?: Record<string, unknown>;
  formId?: string;
} {
  if (!scope) return {};
  return {
    formValues: useGenUiFormsStore.getState().getValues(scope.formKey),
    formId: scope.formId,
  };
}

export function GenUiForm({
  node,
  ctx,
  children,
}: {
  node: GenUiNode;
  ctx: GenUiRenderContextValue;
  children: ReactNode;
}) {
  const p = node.props ?? {};
  const formId = s(p.formId) || node.nodeId;
  const scope = useMemo<GenUiFormScope>(
    () => ({ formId, formKey: formKeyFor(ctx, formId) }),
    [ctx, formId],
  );
  return (
    <GenUiFormContext.Provider value={scope}>
      <div className="space-y-3">
        {(!!p.title || !!p.description) && (
          <div>
            {!!p.title && (
              <h3 className="text-sm font-semibold text-foreground">{s(p.title)}</h3>
            )}
            {!!p.description && (
              <p className="mt-0.5 text-xs text-muted-foreground">{s(p.description)}</p>
            )}
          </div>
        )}
        {children}
      </div>
    </GenUiFormContext.Provider>
  );
}

const FIELD_CLASS =
  'w-full px-3 py-2 text-sm border border-border rounded-lg bg-surface text-foreground ' +
  'focus:outline-none focus:ring-1 focus:ring-primary-400';

function FieldShell({
  p,
  children,
}: {
  p: Record<string, unknown>;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      {!!p.label && (
        <label className="text-xs font-medium text-muted-foreground">
          {s(p.label)}
          {Boolean(p.required) && <span className="ml-0.5 text-red-500">*</span>}
        </label>
      )}
      {children}
      {!!p.description && (
        <p className="text-[11px] text-muted-foreground">{s(p.description)}</p>
      )}
    </div>
  );
}

export type GenUiFieldKind =
  | 'Input'
  | 'Select'
  | 'NumberInput'
  | 'Switch'
  | 'Slider'
  | 'FileInput'
  | 'Textarea';

/**
 * Controlled form field. Binds to the enclosing Form scope when a `name`
 * prop is present; otherwise renders the legacy read-only preview.
 */
export function GenUiFormField({ node }: { node: GenUiNode }) {
  const scope = useContext(GenUiFormContext);
  const p = node.props ?? {};
  const kind = node.kind as GenUiFieldKind;
  const name = s(p.name);
  const interactive = Boolean(scope && name);
  const formKey = scope?.formKey ?? '';

  const setField = useGenUiFormsStore((st) => st.setField);
  const seedField = useGenUiFormsStore((st) => st.seedField);
  const stored = useGenUiFormsStore((st) =>
    interactive ? st.values[formKey]?.[name] : undefined,
  );

  // Seed the initial value once so submit collects untouched defaults too.
  const initialValue = p.value;
  useEffect(() => {
    if (interactive && initialValue !== undefined) {
      seedField(formKey, name, initialValue);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interactive, formKey, name]);

  const value = interactive && stored !== undefined ? stored : p.value;
  const onChange = (v: unknown) => {
    if (interactive) setField(formKey, name, v);
  };

  switch (kind) {
    case 'Textarea':
      return (
        <FieldShell p={p}>
          <textarea
            className={cn(FIELD_CLASS, 'resize-y')}
            rows={typeof p.rows === 'number' ? p.rows : 3}
            placeholder={s(p.placeholder)}
            value={s(value)}
            readOnly={!interactive}
            onChange={(e) => onChange(e.target.value)}
          />
        </FieldShell>
      );

    case 'NumberInput':
      return (
        <FieldShell p={p}>
          <input
            type="number"
            className={FIELD_CLASS}
            value={value === undefined || value === null || value === '' ? '' : Number(value)}
            min={typeof p.min === 'number' ? p.min : undefined}
            max={typeof p.max === 'number' ? p.max : undefined}
            step={typeof p.step === 'number' ? p.step : p.integer ? 1 : 'any'}
            readOnly={!interactive}
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === '') return onChange(undefined);
              onChange(p.integer ? parseInt(raw, 10) : parseFloat(raw));
            }}
          />
        </FieldShell>
      );

    case 'Switch':
      return (
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            {!!p.label && (
              <span className="text-xs font-medium text-foreground">{s(p.label)}</span>
            )}
            {!!p.description && (
              <p className="text-[11px] text-muted-foreground">{s(p.description)}</p>
            )}
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={Boolean(value)}
            disabled={!interactive}
            onClick={() => onChange(!value)}
            className={cn(
              'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors',
              value ? 'bg-primary-500' : 'bg-border',
              !interactive && 'opacity-60',
            )}
          >
            <span
              className={cn(
                'inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform',
                value ? 'translate-x-[18px]' : 'translate-x-0.5',
              )}
            />
          </button>
        </div>
      );

    case 'Slider': {
      const min = typeof p.min === 'number' ? p.min : 0;
      const max = typeof p.max === 'number' ? p.max : 100;
      const num = typeof value === 'number' ? value : min;
      return (
        <FieldShell p={p}>
          <div className="flex items-center gap-2">
            <input
              type="range"
              className="h-1.5 flex-1 cursor-pointer accent-primary-500"
              min={min}
              max={max}
              step={typeof p.step === 'number' ? p.step : 1}
              value={num}
              disabled={!interactive}
              onChange={(e) => onChange(parseFloat(e.target.value))}
            />
            <span className="w-10 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
              {num}
            </span>
          </div>
        </FieldShell>
      );
    }

    case 'FileInput':
      return (
        <FieldShell p={p}>
          <input
            type="text"
            className={FIELD_CLASS}
            placeholder={s(p.accept) ? `file id or path (${s(p.accept)})` : 'file id or path'}
            value={s(value)}
            readOnly={!interactive}
            onChange={(e) => onChange(e.target.value)}
          />
        </FieldShell>
      );

    case 'Select':
      return (
        <FieldShell p={p}>
          <select
            className={cn(FIELD_CLASS, 'appearance-none')}
            value={s(value)}
            disabled={!interactive}
            onChange={(e) => onChange(e.target.value)}
          >
            {!interactive || s(value) ? null : <option value="" />}
            {((p.options as unknown[]) || []).map((opt, i) => (
              <option key={i} value={s(opt)}>
                {s(opt)}
              </option>
            ))}
          </select>
        </FieldShell>
      );

    case 'Input':
    default:
      return (
        <FieldShell p={p}>
          <input
            type={(p.type as string) || 'text'}
            className={FIELD_CLASS}
            placeholder={s(p.placeholder)}
            value={s(value)}
            readOnly={!interactive}
            onChange={(e) => onChange(e.target.value)}
          />
        </FieldShell>
      );
  }
}
