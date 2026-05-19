import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import { Toast, type ToastVariant } from './Toast';
import { cn } from '@/lib/utils';

export interface ToastItem {
  id: string;
  variant?: ToastVariant;
  title?: string;
  description?: string;
  duration?: number;
  action?: ReactNode;
}

interface ToastContextValue {
  toasts: ToastItem[];
  toast: (options: Omit<ToastItem, 'id'>) => string;
  dismiss: (id: string) => void;
  dismissAll: () => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};

interface ToastProviderProps {
  children: ReactNode;
}

export const ToastProvider = ({ children }: ToastProviderProps) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const toast = useCallback((options: Omit<ToastItem, 'id'>) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { ...options, id }]);
    return id;
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const dismissAll = useCallback(() => {
    setToasts([]);
  }, []);

  return (
    <ToastContext.Provider value={{ toasts, toast, dismiss, dismissAll }}>
      {children}
    </ToastContext.Provider>
  );
};

interface ToasterProps {
  position?: 'top-left' | 'top-right' | 'top-center' | 'bottom-left' | 'bottom-right' | 'bottom-center';
  maxToasts?: number;
}

export const Toaster = ({ position = 'top-right', maxToasts = 5 }: ToasterProps) => {
  const { toasts, dismiss } = useToast();

  const visibleToasts = toasts.slice(-maxToasts);

  const positionStyles = {
    'top-left': 'top-4 left-4',
    'top-right': 'top-4 right-4',
    'top-center': 'top-4 left-1/2 -translate-x-1/2',
    'bottom-left': 'bottom-4 left-4',
    'bottom-right': 'bottom-4 right-4',
    'bottom-center': 'bottom-4 left-1/2 -translate-x-1/2',
  };

  return (
    <div
      className={cn(
        'fixed z-[100] flex flex-col gap-2 w-full max-w-sm pointer-events-none',
        positionStyles[position]
      )}
    >
      {visibleToasts.map((toast) => (
        <Toast
          key={toast.id}
          variant={toast.variant}
          title={toast.title}
          description={toast.description}
          duration={toast.duration}
          action={toast.action}
          onClose={() => dismiss(toast.id)}
        />
      ))}
    </div>
  );
};

export const toast = {
  success: (title: string, description?: string) => {
    return { variant: 'success' as const, title, description };
  },
  error: (title: string, description?: string) => {
    return { variant: 'error' as const, title, description };
  },
  warning: (title: string, description?: string) => {
    return { variant: 'warning' as const, title, description };
  },
  info: (title: string, description?: string) => {
    return { variant: 'info' as const, title, description };
  },
};
