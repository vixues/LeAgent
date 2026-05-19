import { useEffect, useRef, useCallback, useState } from 'react';
import { useFlowStore } from '@/stores/flow';
import { useSettingsStore } from '@/stores/settingsStore';
import { useAlertStore } from '@/stores/alertStore';
import { useSaveFlow } from './useSaveFlow';

export interface AutoSaveOptions {
  enabled?: boolean;
  interval?: number;
  saveOnBlur?: boolean;
  saveOnUnload?: boolean;
  debounceMs?: number;
  onSaveStart?: () => void;
  onSaveSuccess?: () => void;
  onSaveError?: (error: Error) => void;
}

export interface AutoSaveState {
  isAutoSaving: boolean;
  lastAutoSaveAt: Date | null;
  nextAutoSaveAt: Date | null;
  autoSaveError: Error | null;
  pendingChanges: boolean;
}

export function useAutoSaveFlow(options: AutoSaveOptions = {}) {
  const {
    enabled: enabledOverride,
    interval: intervalOverride,
    saveOnBlur = true,
    saveOnUnload = true,
    debounceMs = 1000,
    onSaveStart,
    onSaveSuccess,
    onSaveError,
  } = options;

  const { settings } = useSettingsStore();
  const { isDirty, flowId } = useFlowStore();
  const { saveFlow, isSaving } = useSaveFlow();
  const { error: showError } = useAlertStore();

  const enabled = enabledOverride ?? settings.editor.autoSaveEnabled;
  const interval = intervalOverride ?? settings.editor.autoSaveInterval;

  const [state, setState] = useState<AutoSaveState>({
    isAutoSaving: false,
    lastAutoSaveAt: null,
    nextAutoSaveAt: null,
    autoSaveError: null,
    pendingChanges: false,
  });

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSaveAttemptRef = useRef<number>(0);

  const performAutoSave = useCallback(async () => {
    if (!isDirty || isSaving || !flowId) {
      return false;
    }

    const now = Date.now();
    if (now - lastSaveAttemptRef.current < debounceMs) {
      return false;
    }
    lastSaveAttemptRef.current = now;

    setState((prev) => ({
      ...prev,
      isAutoSaving: true,
      autoSaveError: null,
    }));

    onSaveStart?.();

    try {
      await saveFlow();
      const savedAt = new Date();
      setState((prev) => ({
        ...prev,
        isAutoSaving: false,
        lastAutoSaveAt: savedAt,
        nextAutoSaveAt: new Date(savedAt.getTime() + interval),
        pendingChanges: false,
      }));
      onSaveSuccess?.();
      return true;
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Auto-save failed');
      setState((prev) => ({
        ...prev,
        isAutoSaving: false,
        autoSaveError: error,
      }));
      onSaveError?.(error);
      showError(`Auto-save failed: ${error.message}`);
      return false;
    }
  }, [isDirty, isSaving, flowId, debounceMs, saveFlow, interval, onSaveStart, onSaveSuccess, onSaveError, showError]);

  const debouncedSave = useCallback(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      performAutoSave();
    }, debounceMs);
  }, [performAutoSave, debounceMs]);

  useEffect(() => {
    if (!enabled || !flowId) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    setState((prev) => ({
      ...prev,
      nextAutoSaveAt: new Date(Date.now() + interval),
    }));

    intervalRef.current = setInterval(() => {
      performAutoSave();
    }, interval);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [enabled, flowId, interval, performAutoSave]);

  useEffect(() => {
    setState((prev) => ({ ...prev, pendingChanges: isDirty }));
    
    if (enabled && isDirty) {
      debouncedSave();
    }
  }, [enabled, isDirty, debouncedSave]);

  useEffect(() => {
    if (!saveOnBlur || !enabled) return;

    const handleVisibilityChange = () => {
      if (document.hidden && isDirty) {
        performAutoSave();
      }
    };

    const handleBlur = () => {
      if (isDirty) {
        performAutoSave();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleBlur);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('blur', handleBlur);
    };
  }, [saveOnBlur, enabled, isDirty, performAutoSave]);

  useEffect(() => {
    if (!saveOnUnload || !enabled) return;

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (isDirty) {
        performAutoSave();
        event.preventDefault();
        event.returnValue = '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [saveOnUnload, enabled, isDirty, performAutoSave]);

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const forceAutoSave = useCallback(async () => {
    return performAutoSave();
  }, [performAutoSave]);

  const pauseAutoSave = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const resumeAutoSave = useCallback(() => {
    if (enabled && flowId && !intervalRef.current) {
      intervalRef.current = setInterval(performAutoSave, interval);
    }
  }, [enabled, flowId, interval, performAutoSave]);

  return {
    ...state,
    enabled,
    interval,
    forceAutoSave,
    pauseAutoSave,
    resumeAutoSave,
  };
}

export default useAutoSaveFlow;
