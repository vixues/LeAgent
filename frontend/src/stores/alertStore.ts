import { create } from 'zustand';
import { generateId } from '@/lib/utils';

export type AlertType = 'success' | 'error' | 'warning' | 'info';
export type AlertPosition = 'top' | 'top-right' | 'top-left' | 'bottom' | 'bottom-right' | 'bottom-left';

export interface Alert {
  id: string;
  type: AlertType;
  title?: string;
  message: string;
  duration?: number;
  dismissible?: boolean;
  action?: {
    label: string;
    onClick: () => void;
  };
  createdAt: number;
}

interface AlertState {
  alerts: Alert[];
  position: AlertPosition;
  maxAlerts: number;
  defaultDuration: number;

  setPosition: (position: AlertPosition) => void;
  setMaxAlerts: (max: number) => void;
  setDefaultDuration: (duration: number) => void;
  
  addAlert: (alert: Omit<Alert, 'id' | 'createdAt'>) => string;
  removeAlert: (id: string) => void;
  clearAlerts: () => void;
  
  success: (message: string, options?: Partial<Omit<Alert, 'id' | 'type' | 'message' | 'createdAt'>>) => string;
  error: (message: string, options?: Partial<Omit<Alert, 'id' | 'type' | 'message' | 'createdAt'>>) => string;
  warning: (message: string, options?: Partial<Omit<Alert, 'id' | 'type' | 'message' | 'createdAt'>>) => string;
  info: (message: string, options?: Partial<Omit<Alert, 'id' | 'type' | 'message' | 'createdAt'>>) => string;
  notice: (message: string, options?: Partial<Omit<Alert, 'id' | 'type' | 'message' | 'createdAt'>>) => string;
}

const DEFAULT_DURATION = 5000;
const MAX_ALERTS = 5;

const alertTimers = new Map<string, ReturnType<typeof setTimeout>>();

export const useAlertStore = create<AlertState>((set, get) => ({
  alerts: [],
  position: 'top-right',
  maxAlerts: MAX_ALERTS,
  defaultDuration: DEFAULT_DURATION,

  setPosition: (position) => set({ position }),
  setMaxAlerts: (maxAlerts) => set({ maxAlerts }),
  setDefaultDuration: (defaultDuration) => set({ defaultDuration }),

  addAlert: (alertData) => {
    const id = generateId();
    const { maxAlerts, defaultDuration } = get();
    
    const alert: Alert = {
      ...alertData,
      id,
      createdAt: Date.now(),
      duration: alertData.duration ?? defaultDuration,
      dismissible: alertData.dismissible ?? true,
    };

    set((state) => {
      let newAlerts = [...state.alerts, alert];
      
      if (newAlerts.length > maxAlerts) {
        const removed = newAlerts.slice(0, newAlerts.length - maxAlerts);
        removed.forEach((a) => {
          const timer = alertTimers.get(a.id);
          if (timer) {
            clearTimeout(timer);
            alertTimers.delete(a.id);
          }
        });
        newAlerts = newAlerts.slice(-maxAlerts);
      }
      
      return { alerts: newAlerts };
    });

    if (alert.duration && alert.duration > 0) {
      const timer = setTimeout(() => {
        get().removeAlert(id);
      }, alert.duration);
      alertTimers.set(id, timer);
    }

    return id;
  },

  removeAlert: (id) => {
    const timer = alertTimers.get(id);
    if (timer) {
      clearTimeout(timer);
      alertTimers.delete(id);
    }
    
    set((state) => ({
      alerts: state.alerts.filter((a) => a.id !== id),
    }));
  },

  clearAlerts: () => {
    alertTimers.forEach((timer) => clearTimeout(timer));
    alertTimers.clear();
    set({ alerts: [] });
  },

  success: (message, options = {}) => {
    return get().addAlert({
      type: 'success',
      message,
      ...options,
    });
  },

  error: (message, options = {}) => {
    return get().addAlert({
      type: 'error',
      message,
      duration: options.duration ?? 0,
      ...options,
    });
  },

  warning: (message, options = {}) => {
    return get().addAlert({
      type: 'warning',
      message,
      ...options,
    });
  },

  info: (message, options = {}) => {
    return get().addAlert({
      type: 'info',
      message,
      ...options,
    });
  },

  notice: (message, options = {}) => {
    return get().addAlert({
      type: 'info',
      message,
      ...options,
    });
  },
}));

export function useAlert() {
  const { success, error, warning, info, notice, removeAlert, clearAlerts } = useAlertStore();
  return { success, error, warning, info, notice, dismiss: removeAlert, clearAll: clearAlerts };
}
