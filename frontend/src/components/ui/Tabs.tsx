import { createContext, useContext, useState, forwardRef, type ReactNode, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

interface TabsContextType {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

const TabsContext = createContext<TabsContextType | null>(null);

interface TabsProps {
  defaultValue?: string;
  value?: string;
  onValueChange?: (value: string) => void;
  children: ReactNode;
  className?: string;
}

const Tabs = ({ defaultValue = '', value, onValueChange, children, className }: TabsProps) => {
  const [internalValue, setInternalValue] = useState(defaultValue);
  const activeTab = value ?? internalValue;

  const setActiveTab = (tab: string) => {
    if (!value) {
      setInternalValue(tab);
    }
    onValueChange?.(tab);
  };

  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
};
Tabs.displayName = 'Tabs';

const TabsList = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ children, className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'flex gap-1 p-1 bg-gray-100 dark:bg-gray-800 rounded-lg overflow-x-auto scrollbar-thin',
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
);
TabsList.displayName = 'TabsList';

interface TabsTriggerProps extends HTMLAttributes<HTMLButtonElement> {
  value: string;
  children: ReactNode;
  disabled?: boolean;
}

const TabsTrigger = forwardRef<HTMLButtonElement, TabsTriggerProps>(
  ({ value, children, className, disabled, ...props }, ref) => {
    const context = useContext(TabsContext);
    if (!context) throw new Error('TabsTrigger must be used within Tabs');

    const { activeTab, setActiveTab } = context;
    const isActive = activeTab === value;

    return (
      <button
        ref={ref}
        type="button"
        disabled={disabled}
        onClick={() => setActiveTab(value)}
        className={cn(
          'inline-flex items-center justify-center gap-2 whitespace-nowrap',
          'px-4 py-2 text-sm font-medium rounded-md transition-colors duration-200',
          'focus:outline-none focus:ring-2 focus:ring-primary-500/20',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          isActive
            ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
            : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white',
          className
        )}
        {...props}
      >
        {children}
      </button>
    );
  }
);
TabsTrigger.displayName = 'TabsTrigger';

interface TabsContentProps {
  value: string;
  children: ReactNode;
  className?: string;
}

const TabsContent = forwardRef<HTMLDivElement, TabsContentProps & HTMLAttributes<HTMLDivElement>>(
  ({ value, children, className, ...props }, ref) => {
    const context = useContext(TabsContext);
    if (!context) throw new Error('TabsContent must be used within Tabs');

    const { activeTab } = context;
    if (activeTab !== value) return null;

    return (
      <div ref={ref} className={cn('animate-in', className)} {...props}>
        {children}
      </div>
    );
  }
);
TabsContent.displayName = 'TabsContent';

export { Tabs, TabsList, TabsTrigger, TabsContent };
