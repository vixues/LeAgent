import { create } from 'zustand';

/**
 * Field values for interactive GenUi `Form` scopes, keyed by a stable form
 * key (`scope::formId`). Named fields (Input, Select, NumberInput, Switch,
 * Slider, FileInput, Textarea) bind here; form-aware buttons collect the
 * values when dispatching `submit_form` / `run_workflow` / `resume_workflow`.
 */
interface GenUiFormsState {
  values: Record<string, Record<string, unknown>>;
  setField: (formKey: string, name: string, value: unknown) => void;
  /** Seed a field's initial value without clobbering user edits. */
  seedField: (formKey: string, name: string, value: unknown) => void;
  getValues: (formKey: string) => Record<string, unknown>;
  clearForm: (formKey: string) => void;
}

export const useGenUiFormsStore = create<GenUiFormsState>()((set, get) => ({
  values: {},

  setField(formKey, name, value) {
    set((s) => ({
      values: {
        ...s.values,
        [formKey]: { ...(s.values[formKey] ?? {}), [name]: value },
      },
    }));
  },

  seedField(formKey, name, value) {
    const current = get().values[formKey];
    if (current && name in current) return;
    if (value === undefined) return;
    set((s) => ({
      values: {
        ...s.values,
        [formKey]: { ...(s.values[formKey] ?? {}), [name]: value },
      },
    }));
  },

  getValues(formKey) {
    return get().values[formKey] ?? {};
  },

  clearForm(formKey) {
    set((s) => {
      if (!(formKey in s.values)) return s;
      const next = { ...s.values };
      delete next[formKey];
      return { values: next };
    });
  },
}));
