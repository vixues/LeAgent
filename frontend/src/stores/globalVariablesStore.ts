import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { apiClient } from '@/api/client';


export type VariableType = 'string' | 'number' | 'boolean' | 'json' | 'secret';
export type VariableScope = 'global' | 'workspace' | 'flow';

export interface GlobalVariable {
  id: string;
  name: string;
  value: unknown;
  type: VariableType;
  scope: VariableScope;
  description?: string;
  isSecret: boolean;
  tags?: string[];
  createdAt: string;
  updatedAt: string;
  createdBy?: string;
}

export interface VariableReference {
  variableId: string;
  flowId?: string;
  nodeId?: string;
  parameterPath: string;
}

interface GlobalVariablesState {
  variables: GlobalVariable[];
  references: VariableReference[];
  isLoading: boolean;
  error: string | null;

  fetchVariables: () => Promise<void>;
  createVariable: (variable: Omit<GlobalVariable, 'id' | 'createdAt' | 'updatedAt'>) => Promise<GlobalVariable>;
  updateVariable: (id: string, updates: Partial<GlobalVariable>) => Promise<void>;
  deleteVariable: (id: string) => Promise<void>;
  
  getVariable: (id: string) => GlobalVariable | undefined;
  getVariableByName: (name: string, scope?: VariableScope) => GlobalVariable | undefined;
  getVariablesByScope: (scope: VariableScope) => GlobalVariable[];
  getVariablesByTag: (tag: string) => GlobalVariable[];
  
  getValue: (nameOrId: string) => unknown;
  setValue: (nameOrId: string, value: unknown) => Promise<void>;
  
  resolveVariables: (template: string, context?: Record<string, unknown>) => string;
  extractVariableNames: (template: string) => string[];
  
  addReference: (reference: Omit<VariableReference, 'id'>) => void;
  removeReference: (variableId: string, flowId?: string, nodeId?: string) => void;
  getReferences: (variableId: string) => VariableReference[];
  
  validateVariableName: (name: string, excludeId?: string) => { valid: boolean; message?: string };
  exportVariables: (scope?: VariableScope) => string;
  importVariables: (json: string) => Promise<number>;
}

const VARIABLE_PATTERN = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g;

export const useGlobalVariablesStore = create<GlobalVariablesState>()(
  persist(
    (set, get) => ({
      variables: [],
      references: [],
      isLoading: false,
      error: null,

      fetchVariables: async () => {
        set({ isLoading: true, error: null });
        try {
          const variables = await apiClient.get<GlobalVariable[]>('/variables');
          set({ variables, isLoading: false });
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to fetch variables';
          set({ error: message, isLoading: false });
        }
      },

      createVariable: async (variableData) => {
        const validation = get().validateVariableName(variableData.name);
        if (!validation.valid) {
          throw new Error(validation.message);
        }

        set({ isLoading: true, error: null });
        try {
          const variable = await apiClient.post<GlobalVariable>('/variables', variableData);
          set((state) => ({
            variables: [...state.variables, variable],
            isLoading: false,
          }));
          return variable;
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to create variable';
          set({ error: message, isLoading: false });
          throw err;
        }
      },

      updateVariable: async (id, updates) => {
        if (updates.name) {
          const validation = get().validateVariableName(updates.name, id);
          if (!validation.valid) {
            throw new Error(validation.message);
          }
        }

        set({ isLoading: true, error: null });
        try {
          const variable = await apiClient.put<GlobalVariable>(`/variables/${id}`, updates);
          set((state) => ({
            variables: state.variables.map((v) => (v.id === id ? variable : v)),
            isLoading: false,
          }));
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to update variable';
          set({ error: message, isLoading: false });
          throw err;
        }
      },

      deleteVariable: async (id) => {
        set({ isLoading: true, error: null });
        try {
          await apiClient.delete(`/variables/${id}`);
          set((state) => ({
            variables: state.variables.filter((v) => v.id !== id),
            references: state.references.filter((r) => r.variableId !== id),
            isLoading: false,
          }));
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to delete variable';
          set({ error: message, isLoading: false });
          throw err;
        }
      },

      getVariable: (id) => get().variables.find((v) => v.id === id),

      getVariableByName: (name, scope) => {
        const { variables } = get();
        if (scope) {
          return variables.find((v) => v.name === name && v.scope === scope);
        }
        return variables.find((v) => v.name === name);
      },

      getVariablesByScope: (scope) =>
        get().variables.filter((v) => v.scope === scope),

      getVariablesByTag: (tag) =>
        get().variables.filter((v) => v.tags?.includes(tag)),

      getValue: (nameOrId) => {
        const { variables } = get();
        const variable = variables.find((v) => v.id === nameOrId || v.name === nameOrId);
        if (!variable) return undefined;
        if (variable.isSecret) return '********';
        return variable.value;
      },

      setValue: async (nameOrId, value) => {
        const { variables, updateVariable } = get();
        const variable = variables.find((v) => v.id === nameOrId || v.name === nameOrId);
        if (!variable) {
          throw new Error(`Variable not found: ${nameOrId}`);
        }
        await updateVariable(variable.id, { value });
      },

      resolveVariables: (template, context = {}) => {
        const { variables } = get();
        
        return template.replace(VARIABLE_PATTERN, (match, varName) => {
          if (varName in context) {
            return String(context[varName]);
          }
          
          const variable = variables.find((v) => v.name === varName);
          if (variable) {
            if (variable.isSecret) return match;
            return String(variable.value);
          }
          
          return match;
        });
      },

      extractVariableNames: (template) => {
        const matches = template.matchAll(VARIABLE_PATTERN);
        return [...new Set([...matches].map((m) => m[1]))].filter((s): s is string => s !== undefined);
      },

      addReference: (reference) => {
        set((state) => ({
          references: [...state.references, reference],
        }));
      },

      removeReference: (variableId, flowId, nodeId) => {
        set((state) => ({
          references: state.references.filter((r) => {
            if (r.variableId !== variableId) return true;
            if (flowId && r.flowId !== flowId) return true;
            if (nodeId && r.nodeId !== nodeId) return true;
            return false;
          }),
        }));
      },

      getReferences: (variableId) =>
        get().references.filter((r) => r.variableId === variableId),

      validateVariableName: (name, excludeId) => {
        if (!name) {
          return { valid: false, message: 'Variable name is required' };
        }
        if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(name)) {
          return {
            valid: false,
            message: 'Variable name must start with a letter or underscore and contain only alphanumeric characters',
          };
        }
        if (name.length > 64) {
          return { valid: false, message: 'Variable name must be 64 characters or less' };
        }
        
        const existing = get().variables.find((v) => v.name === name && v.id !== excludeId);
        if (existing) {
          return { valid: false, message: 'A variable with this name already exists' };
        }
        
        return { valid: true };
      },

      exportVariables: (scope) => {
        let vars = get().variables;
        if (scope) {
          vars = vars.filter((v) => v.scope === scope);
        }
        
        const exportData = vars.map((v) => ({
          name: v.name,
          value: v.isSecret ? null : v.value,
          type: v.type,
          scope: v.scope,
          description: v.description,
          isSecret: v.isSecret,
          tags: v.tags,
        }));
        
        return JSON.stringify(exportData, null, 2);
      },

      importVariables: async (json) => {
        try {
          const imported = JSON.parse(json) as Array<Omit<GlobalVariable, 'id' | 'createdAt' | 'updatedAt'>>;
          let count = 0;
          
          for (const varData of imported) {
            try {
              await get().createVariable(varData);
              count++;
            } catch {
              // Skip variables that fail validation
            }
          }
          
          return count;
        } catch {
          throw new Error('Invalid JSON format');
        }
      },
    }),
    {
      name: 'leagent-global-variables',
      partialize: () => ({}),
    }
  )
);
