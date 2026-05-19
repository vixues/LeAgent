import { useCallback, useEffect, useState, useRef } from 'react';
import { useFlowStore } from '@/stores/flow';
import { useSettingsStore } from '@/stores/settingsStore';

export interface UnsavedChangesOptions {
  enabled?: boolean;
  warnOnNavigation?: boolean;
  warnOnClose?: boolean;
  trackFormChanges?: boolean;
  customMessage?: string;
}

export interface UnsavedChangesState {
  hasUnsavedChanges: boolean;
  changeCount: number;
  lastChangeAt: Date | null;
  trackedFields: Map<string, { original: unknown; current: unknown }>;
}

export interface ChangeTracker {
  trackField: (fieldId: string, originalValue: unknown) => void;
  updateField: (fieldId: string, currentValue: unknown) => void;
  untrackField: (fieldId: string) => void;
  resetField: (fieldId: string) => void;
  resetAll: () => void;
}

export function useUnsavedChanges(options: UnsavedChangesOptions = {}) {
  const {
    enabled = true,
    warnOnClose = true,
    trackFormChanges = false,
    customMessage = 'You have unsaved changes. Are you sure you want to leave?',
  } = options;

  const { isDirty } = useFlowStore();
  useSettingsStore();

  const [state, setState] = useState<UnsavedChangesState>({
    hasUnsavedChanges: false,
    changeCount: 0,
    lastChangeAt: null,
    trackedFields: new Map(),
  });

  const originalValuesRef = useRef<Map<string, unknown>>(new Map());

  const computeHasChanges = useCallback(() => {
    if (isDirty) return true;

    for (const [, field] of state.trackedFields) {
      if (JSON.stringify(field.original) !== JSON.stringify(field.current)) {
        return true;
      }
    }

    return false;
  }, [isDirty, state.trackedFields]);

  useEffect(() => {
    const hasChanges = computeHasChanges();
    if (hasChanges !== state.hasUnsavedChanges) {
      setState((prev) => ({
        ...prev,
        hasUnsavedChanges: hasChanges,
        lastChangeAt: hasChanges ? new Date() : prev.lastChangeAt,
      }));
    }
  }, [computeHasChanges, state.hasUnsavedChanges]);

  const trackField = useCallback((fieldId: string, originalValue: unknown) => {
    if (!trackFormChanges) return;

    originalValuesRef.current.set(fieldId, originalValue);
    setState((prev) => {
      const newTrackedFields = new Map(prev.trackedFields);
      newTrackedFields.set(fieldId, {
        original: originalValue,
        current: originalValue,
      });
      return { ...prev, trackedFields: newTrackedFields };
    });
  }, [trackFormChanges]);

  const updateField = useCallback((fieldId: string, currentValue: unknown) => {
    if (!trackFormChanges) return;

    setState((prev) => {
      const existing = prev.trackedFields.get(fieldId);
      if (!existing) return prev;

      const newTrackedFields = new Map(prev.trackedFields);
      newTrackedFields.set(fieldId, {
        ...existing,
        current: currentValue,
      });

      const hasChange =
        JSON.stringify(existing.original) !== JSON.stringify(currentValue);

      return {
        ...prev,
        trackedFields: newTrackedFields,
        changeCount: prev.changeCount + (hasChange ? 1 : 0),
        lastChangeAt: hasChange ? new Date() : prev.lastChangeAt,
      };
    });
  }, [trackFormChanges]);

  const untrackField = useCallback((fieldId: string) => {
    originalValuesRef.current.delete(fieldId);
    setState((prev) => {
      const newTrackedFields = new Map(prev.trackedFields);
      newTrackedFields.delete(fieldId);
      return { ...prev, trackedFields: newTrackedFields };
    });
  }, []);

  const resetField = useCallback((fieldId: string) => {
    const original = originalValuesRef.current.get(fieldId);
    if (original !== undefined) {
      setState((prev) => {
        const newTrackedFields = new Map(prev.trackedFields);
        newTrackedFields.set(fieldId, {
          original,
          current: original,
        });
        return { ...prev, trackedFields: newTrackedFields };
      });
    }
  }, []);

  const resetAll = useCallback(() => {
    setState((prev) => {
      const newTrackedFields = new Map<string, { original: unknown; current: unknown }>();
      for (const [fieldId, field] of prev.trackedFields) {
        newTrackedFields.set(fieldId, {
          original: field.original,
          current: field.original,
        });
      }
      return {
        ...prev,
        trackedFields: newTrackedFields,
        hasUnsavedChanges: isDirty,
        changeCount: 0,
      };
    });
  }, [isDirty]);

  useEffect(() => {
    if (!enabled || !warnOnClose) return;

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (state.hasUnsavedChanges) {
        event.preventDefault();
        event.returnValue = customMessage;
        return customMessage;
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [enabled, warnOnClose, state.hasUnsavedChanges, customMessage]);

  const confirmNavigation = useCallback((callback: () => void) => {
    if (!state.hasUnsavedChanges) {
      callback();
      return;
    }

    if (window.confirm(customMessage)) {
      callback();
    }
  }, [state.hasUnsavedChanges, customMessage]);

  const getChangedFields = useCallback(() => {
    const changed: Array<{ fieldId: string; original: unknown; current: unknown }> = [];
    for (const [fieldId, field] of state.trackedFields) {
      if (JSON.stringify(field.original) !== JSON.stringify(field.current)) {
        changed.push({ fieldId, ...field });
      }
    }
    return changed;
  }, [state.trackedFields]);

  const isFieldChanged = useCallback((fieldId: string) => {
    const field = state.trackedFields.get(fieldId);
    if (!field) return false;
    return JSON.stringify(field.original) !== JSON.stringify(field.current);
  }, [state.trackedFields]);

  const changeTracker: ChangeTracker = {
    trackField,
    updateField,
    untrackField,
    resetField,
    resetAll,
  };

  return {
    ...state,
    ...changeTracker,
    confirmNavigation,
    getChangedFields,
    isFieldChanged,
    enabled,
  };
}

export default useUnsavedChanges;
