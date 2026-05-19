import { forwardRef, type InputHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export interface SwitchProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'size'> {
  label?: string;
  size?: 'sm' | 'md' | 'lg';
  onCheckedChange?: (checked: boolean) => void;
}

const Switch = forwardRef<HTMLInputElement, SwitchProps>(
  ({ className, label, size = 'md', checked, onChange, onCheckedChange, disabled, ...props }, ref) => {
    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      onChange?.(e);
      onCheckedChange?.(e.target.checked);
    };
    const sizes = {
      sm: { track: 'w-8 h-4', thumb: 'w-3 h-3', translate: 'translate-x-4' },
      md: { track: 'w-10 h-5', thumb: 'w-4 h-4', translate: 'translate-x-5' },
      lg: { track: 'w-12 h-6', thumb: 'w-5 h-5', translate: 'translate-x-6' },
    };

    const sizeConfig = sizes[size];

    return (
      <label
        className={cn(
          'inline-flex items-center gap-2 cursor-pointer',
          disabled && 'opacity-50 cursor-not-allowed',
          className
        )}
      >
        <div className="relative">
          <input
            ref={ref}
            type="checkbox"
            className="sr-only peer"
            checked={checked}
            onChange={handleChange}
            disabled={disabled}
            {...props}
          />
          <div
            className={cn(
              sizeConfig.track,
              'rounded-full transition-colors duration-200',
              'bg-gray-300 dark:bg-gray-600',
              'peer-checked:bg-primary-600 dark:peer-checked:bg-primary-500',
              'peer-focus:ring-2 peer-focus:ring-primary-500/20'
            )}
          />
          <div
            className={cn(
              sizeConfig.thumb,
              'absolute top-0.5 left-0.5 bg-white rounded-full shadow-sm transition-transform duration-200',
              checked && sizeConfig.translate
            )}
          />
        </div>
        {label && (
          <span className="text-sm text-gray-700 dark:text-gray-300">{label}</span>
        )}
      </label>
    );
  }
);

Switch.displayName = 'Switch';

export { Switch };
