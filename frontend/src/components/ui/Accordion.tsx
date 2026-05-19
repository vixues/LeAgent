import {
  forwardRef,
  createContext,
  useContext,
  useState,
  type ReactNode,
  type HTMLAttributes,
  useCallback,
} from 'react';
import { cn } from '@/lib/utils';
import { ChevronDown } from 'lucide-react';

interface AccordionContextValue {
  value: string | string[];
  onValueChange: (value: string) => void;
  type: 'single' | 'multiple';
  collapsible: boolean;
}

const AccordionContext = createContext<AccordionContextValue | undefined>(undefined);

const useAccordionContext = () => {
  const context = useContext(AccordionContext);
  if (!context) {
    throw new Error('Accordion components must be used within an Accordion');
  }
  return context;
};

interface AccordionItemContextValue {
  value: string;
  isOpen: boolean;
}

const AccordionItemContext = createContext<AccordionItemContextValue | undefined>(undefined);

const useAccordionItemContext = () => {
  const context = useContext(AccordionItemContext);
  if (!context) {
    throw new Error('AccordionItem components must be used within an AccordionItem');
  }
  return context;
};

interface AccordionSingleProps {
  type: 'single';
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  collapsible?: boolean;
  children: ReactNode;
  className?: string;
}

interface AccordionMultipleProps {
  type: 'multiple';
  value?: string[];
  defaultValue?: string[];
  onValueChange?: (value: string[]) => void;
  children: ReactNode;
  className?: string;
}

type AccordionProps = AccordionSingleProps | AccordionMultipleProps;

const Accordion = forwardRef<HTMLDivElement, AccordionProps & HTMLAttributes<HTMLDivElement>>(
  (props, ref) => {
    const { type, children, className, ...rest } = props;

    const isSingle = type === 'single';
    const collapsible = isSingle ? (props as AccordionSingleProps).collapsible ?? false : true;

    const [uncontrolledValue, setUncontrolledValue] = useState<string | string[]>(() => {
      if (isSingle) {
        return (props as AccordionSingleProps).defaultValue ?? '';
      }
      return (props as AccordionMultipleProps).defaultValue ?? [];
    });

    const value = isSingle
      ? (props as AccordionSingleProps).value ?? uncontrolledValue
      : (props as AccordionMultipleProps).value ?? uncontrolledValue;

    const onValueChange = useCallback(
      (itemValue: string) => {
        if (isSingle) {
          const singleProps = props as AccordionSingleProps;
          const newValue = value === itemValue && collapsible ? '' : itemValue;
          if (singleProps.value === undefined) {
            setUncontrolledValue(newValue);
          }
          singleProps.onValueChange?.(newValue as string);
        } else {
          const multipleProps = props as AccordionMultipleProps;
          const currentValue = value as string[];
          const newValue = currentValue.includes(itemValue)
            ? currentValue.filter((v) => v !== itemValue)
            : [...currentValue, itemValue];
          if (multipleProps.value === undefined) {
            setUncontrolledValue(newValue);
          }
          multipleProps.onValueChange?.(newValue);
        }
      },
      [isSingle, value, collapsible, props]
    );

    return (
      <AccordionContext.Provider value={{ value, onValueChange, type, collapsible }}>
        <div ref={ref} className={cn('divide-y divide-gray-200 dark:divide-gray-700', className)} {...rest}>
          {children}
        </div>
      </AccordionContext.Provider>
    );
  }
);

Accordion.displayName = 'Accordion';

interface AccordionItemProps extends HTMLAttributes<HTMLDivElement> {
  value: string;
  disabled?: boolean;
}

const AccordionItem = forwardRef<HTMLDivElement, AccordionItemProps>(
  ({ className, value, disabled, children, ...props }, ref) => {
    const { value: accordionValue, type } = useAccordionContext();

    const isOpen =
      type === 'single'
        ? accordionValue === value
        : (accordionValue as string[]).includes(value);

    return (
      <AccordionItemContext.Provider value={{ value, isOpen }}>
        <div
          ref={ref}
          data-state={isOpen ? 'open' : 'closed'}
          data-disabled={disabled ? '' : undefined}
          className={cn('', disabled && 'opacity-50 cursor-not-allowed', className)}
          {...props}
        >
          {children}
        </div>
      </AccordionItemContext.Provider>
    );
  }
);

AccordionItem.displayName = 'AccordionItem';

interface AccordionTriggerProps extends HTMLAttributes<HTMLButtonElement> {}

const AccordionTrigger = forwardRef<HTMLButtonElement, AccordionTriggerProps>(
  ({ className, children, ...props }, ref) => {
    const { onValueChange } = useAccordionContext();
    const { value, isOpen } = useAccordionItemContext();

    return (
      <button
        ref={ref}
        type="button"
        aria-expanded={isOpen}
        onClick={() => onValueChange(value)}
        className={cn(
          'flex w-full items-center justify-between py-4 text-left',
          'text-sm font-medium text-gray-900 dark:text-white',
          'hover:underline transition-[color,background-color,opacity]',
          '[&[data-state=open]>svg]:rotate-180',
          className
        )}
        data-state={isOpen ? 'open' : 'closed'}
        {...props}
      >
        {children}
        <ChevronDown
          className={cn(
            'h-4 w-4 shrink-0 text-gray-500 transition-transform duration-200',
            isOpen && 'rotate-180'
          )}
        />
      </button>
    );
  }
);

AccordionTrigger.displayName = 'AccordionTrigger';

interface AccordionContentProps extends HTMLAttributes<HTMLDivElement> {}

const AccordionContent = forwardRef<HTMLDivElement, AccordionContentProps>(
  ({ className, children, ...props }, ref) => {
    const { isOpen } = useAccordionItemContext();

    return (
      <div
        ref={ref}
        data-state={isOpen ? 'open' : 'closed'}
        className={cn(
          'overflow-hidden text-sm text-gray-600 dark:text-gray-400',
          'transition-[max-height,opacity] duration-200',
          isOpen ? 'animate-accordion-down' : 'animate-accordion-up hidden',
          className
        )}
        {...props}
      >
        <div className="pb-4">{children}</div>
      </div>
    );
  }
);

AccordionContent.displayName = 'AccordionContent';

export { Accordion, AccordionItem, AccordionTrigger, AccordionContent };
