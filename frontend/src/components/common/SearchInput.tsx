import { forwardRef, useState, useRef, useEffect, type InputHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';
import { Search, X, Loader2 } from 'lucide-react';
import { debounce } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

interface SearchInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'size' | 'onSubmit'> {
  value?: string;
  onChange?: (value: string) => void;
  /** Debounced commit (typing settled). */
  onSearch?: (value: string) => void;
  /** Immediate commit on Enter (optional; falls back to onSearch). */
  onSubmit?: (value: string) => void;
  debounceMs?: number;
  loading?: boolean;
  /**
   * When true, disable the field while `loading`. Default false so typing
   * is not blocked by in-flight searches.
   */
  disableOnLoading?: boolean;
  showClear?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

const SearchInput = forwardRef<HTMLInputElement, SearchInputProps>(
  (
    {
      className,
      value: controlledValue,
      onChange,
      onSearch,
      onSubmit,
      debounceMs = 300,
      loading = false,
      disableOnLoading = false,
      showClear = true,
      size = 'md',
      placeholder,
      disabled,
      ...props
    },
    ref
  ) => {
    const { t } = useTranslation();
    const [uncontrolledValue, setUncontrolledValue] = useState('');
    const isControlled = controlledValue !== undefined;
    const value = isControlled ? controlledValue : uncontrolledValue;

    const debouncedSearchRef = useRef<ReturnType<typeof debounce<(value: string) => void>> | undefined>(undefined);

    useEffect(() => {
      if (onSearch) {
        debouncedSearchRef.current = debounce((searchValue: string) => {
          onSearch(searchValue);
        }, debounceMs);
      }
      return () => {
        debouncedSearchRef.current = undefined;
      };
    }, [onSearch, debounceMs]);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const newValue = e.target.value;
      if (!isControlled) {
        setUncontrolledValue(newValue);
      }
      onChange?.(newValue);
      debouncedSearchRef.current?.(newValue);
    };

    const handleClear = () => {
      if (!isControlled) {
        setUncontrolledValue('');
      }
      onChange?.('');
      onSubmit?.('');
      onSearch?.('');
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' && (onSubmit || onSearch)) {
        e.preventDefault();
        (onSubmit ?? onSearch)?.(value);
      }
      if (e.key === 'Escape' && value) {
        handleClear();
      }
    };

    const sizes = {
      sm: {
        container: 'h-8',
        input: 'text-xs px-8',
        icon: 'w-3.5 h-3.5 left-2.5',
        clear: 'right-2 p-0.5',
      },
      md: {
        container: 'h-10',
        input: 'text-sm px-10',
        icon: 'w-4 h-4 left-3',
        clear: 'right-3 p-1',
      },
      lg: {
        container: 'h-12',
        input: 'text-base px-12',
        icon: 'w-5 h-5 left-4',
        clear: 'right-4 p-1.5',
      },
    };

    const sizeConfig = sizes[size];
    const inputDisabled = Boolean(disabled || (disableOnLoading && loading));

    return (
      <div className={cn('relative', className)}>
        <div
          className={cn(
            'absolute top-1/2 -translate-y-1/2 text-gray-400',
            sizeConfig.icon
          )}
        >
          {loading ? (
            <Loader2 className="animate-spin" />
          ) : (
            <Search className="w-full h-full" />
          )}
        </div>
        <input
          ref={ref}
          type="text"
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          disabled={inputDisabled}
          placeholder={placeholder || t('common.search')}
          className={cn(
            'w-full rounded-lg border transition-colors',
            'bg-surface',
            'border-gray-300 dark:border-gray-600',
            'text-gray-900 dark:text-white',
            'placeholder:text-gray-400 dark:placeholder:text-gray-500',
            'focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            sizeConfig.container,
            sizeConfig.input
          )}
          {...props}
        />
        {showClear && value && !loading && (
          <button
            type="button"
            onClick={handleClear}
            disabled={inputDisabled}
            className={cn(
              'absolute top-1/2 -translate-y-1/2 rounded-md',
              'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300',
              'hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              sizeConfig.clear
            )}
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    );
  }
);

SearchInput.displayName = 'SearchInput';

export { SearchInput };
