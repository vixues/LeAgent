import {
  forwardRef,
  createContext,
  useContext,
  useState,
  useMemo,
  type HTMLAttributes,
  type InputHTMLAttributes,
} from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Search } from 'lucide-react';

interface CommandContextValue {
  search: string;
  setSearch: (search: string) => void;
  selectedIndex: number;
  setSelectedIndex: (index: number) => void;
}

const CommandContext = createContext<CommandContextValue | undefined>(undefined);

const useCommandContext = () => {
  const context = useContext(CommandContext);
  if (!context) {
    throw new Error('Command components must be used within a Command');
  }
  return context;
};

interface CommandProps extends HTMLAttributes<HTMLDivElement> {
  shouldFilter?: boolean;
  filter?: (value: string, search: string) => number;
  loop?: boolean;
}

const Command = forwardRef<HTMLDivElement, CommandProps>(
  ({ className, children, shouldFilter = true, filter, loop = false, ...props }, ref) => {
    const [search, setSearch] = useState('');
    const [selectedIndex, setSelectedIndex] = useState(0);

    return (
      <CommandContext.Provider value={{ search, setSearch, selectedIndex, setSelectedIndex }}>
        <div
          ref={ref}
          className={cn(
            'flex flex-col overflow-hidden rounded-lg',
            'bg-surface',
            'border border-gray-200 dark:border-gray-700',
            className
          )}
          {...props}
        >
          {children}
        </div>
      </CommandContext.Provider>
    );
  }
);

Command.displayName = 'Command';

interface CommandDialogProps extends HTMLAttributes<HTMLDivElement> {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

const CommandDialog = forwardRef<HTMLDivElement, CommandDialogProps>(
  ({ className, children, open, onOpenChange, ...props }, ref) => {
    if (!open) return null;

    return (
      <>
        <div
          className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
          onClick={() => onOpenChange?.(false)}
        />
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh] p-4">
          <Command
            ref={ref}
            className={cn(
              'w-full max-w-lg shadow-xl animate-in fade-in-0 zoom-in-95',
              className
            )}
            {...props}
          >
            {children}
          </Command>
        </div>
      </>
    );
  }
);

CommandDialog.displayName = 'CommandDialog';

interface CommandInputProps extends InputHTMLAttributes<HTMLInputElement> {}

const CommandInput = forwardRef<HTMLInputElement, CommandInputProps>(
  ({ className, placeholder, ...props }, ref) => {
    const { t } = useTranslation();
    const { search, setSearch } = useCommandContext();

    return (
      <div className="flex items-center border-b border-gray-200 dark:border-gray-700 px-3">
        <Search className="mr-2 h-4 w-4 shrink-0 text-gray-400" />
        <input
          ref={ref}
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={placeholder ?? t('command.searchPlaceholder')}
          className={cn(
            'flex h-11 w-full bg-transparent py-3 text-sm outline-none',
            'text-gray-900 dark:text-white',
            'placeholder:text-gray-400 dark:placeholder:text-gray-500',
            'disabled:cursor-not-allowed disabled:opacity-50',
            className
          )}
          {...props}
        />
      </div>
    );
  }
);

CommandInput.displayName = 'CommandInput';

interface CommandListProps extends HTMLAttributes<HTMLDivElement> {}

const CommandList = forwardRef<HTMLDivElement, CommandListProps>(
  ({ className, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn('max-h-[300px] overflow-y-auto overflow-x-hidden', className)}
        {...props}
      >
        {children}
      </div>
    );
  }
);

CommandList.displayName = 'CommandList';

interface CommandEmptyProps extends HTMLAttributes<HTMLDivElement> {}

const CommandEmpty = forwardRef<HTMLDivElement, CommandEmptyProps>(
  ({ className, children, ...props }, ref) => {
    const { t } = useTranslation();
    const { search } = useCommandContext();

    if (!search) return null;

    return (
      <div
        ref={ref}
        className={cn('py-6 text-center text-sm text-gray-500 dark:text-gray-400', className)}
        {...props}
      >
        {children || t('command.noResults')}
      </div>
    );
  }
);

CommandEmpty.displayName = 'CommandEmpty';

interface CommandGroupProps extends HTMLAttributes<HTMLDivElement> {
  heading?: string;
}

const CommandGroup = forwardRef<HTMLDivElement, CommandGroupProps>(
  ({ className, heading, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn('overflow-hidden p-1', className)}
        {...props}
      >
        {heading && (
          <div className="px-2 py-1.5 text-xs font-medium text-gray-500 dark:text-gray-400">
            {heading}
          </div>
        )}
        {children}
      </div>
    );
  }
);

CommandGroup.displayName = 'CommandGroup';

interface CommandItemProps extends Omit<HTMLAttributes<HTMLDivElement>, 'onSelect'> {
  value?: string;
  disabled?: boolean;
  onSelect?: (value: string) => void;
  keywords?: string[];
}

const CommandItem = forwardRef<HTMLDivElement, CommandItemProps>(
  ({ className, children, value, disabled, onSelect, keywords = [], ...props }, ref) => {
    const { search } = useCommandContext();

    const isVisible = useMemo(() => {
      if (!search) return true;
      const searchLower = search.toLowerCase();
      const valueLower = (value || '').toLowerCase();
      const keywordsLower = keywords.map((k) => k.toLowerCase());
      return (
        valueLower.includes(searchLower) ||
        keywordsLower.some((k) => k.includes(searchLower))
      );
    }, [search, value, keywords]);

    if (!isVisible) return null;

    return (
      <div
        ref={ref}
        role="option"
        aria-selected={false}
        aria-disabled={disabled}
        data-disabled={disabled ? '' : undefined}
        className={cn(
          'relative flex cursor-pointer select-none items-center rounded-md px-2 py-1.5',
          'text-sm text-gray-700 dark:text-gray-300',
          'hover:bg-gray-100 dark:hover:bg-gray-800',
          'focus:bg-gray-100 dark:focus:bg-gray-800 outline-none',
          disabled && 'opacity-50 cursor-not-allowed pointer-events-none',
          className
        )}
        onClick={() => !disabled && onSelect?.(value || '')}
        {...props}
      >
        {children}
      </div>
    );
  }
);

CommandItem.displayName = 'CommandItem';

interface CommandSeparatorProps extends HTMLAttributes<HTMLDivElement> {}

const CommandSeparator = forwardRef<HTMLDivElement, CommandSeparatorProps>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('my-1 h-px bg-gray-200 dark:bg-gray-700', className)}
      {...props}
    />
  )
);

CommandSeparator.displayName = 'CommandSeparator';

interface CommandShortcutProps extends HTMLAttributes<HTMLSpanElement> {}

const CommandShortcut = ({ className, ...props }: CommandShortcutProps) => (
  <span
    className={cn('ml-auto text-xs tracking-widest text-gray-400 dark:text-gray-500', className)}
    {...props}
  />
);

CommandShortcut.displayName = 'CommandShortcut';

export {
  Command,
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandSeparator,
  CommandShortcut,
};
