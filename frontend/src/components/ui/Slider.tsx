import { forwardRef, useState, useRef, useCallback, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

interface SliderProps extends Omit<HTMLAttributes<HTMLDivElement>, 'onChange' | 'defaultValue'> {
  value?: number[];
  defaultValue?: number[];
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  orientation?: 'horizontal' | 'vertical';
  onValueChange?: (value: number[]) => void;
  onValueCommit?: (value: number[]) => void;
}

const Slider = forwardRef<HTMLDivElement, SliderProps>(
  (
    {
      className,
      value: controlledValue,
      defaultValue = [0],
      min = 0,
      max = 100,
      step = 1,
      disabled = false,
      orientation = 'horizontal',
      onValueChange,
      onValueCommit,
      ...props
    },
    ref
  ) => {
    const [uncontrolledValue, setUncontrolledValue] = useState(defaultValue);
    const trackRef = useRef<HTMLDivElement>(null);
    const isDragging = useRef(false);

    const isControlled = controlledValue !== undefined;
    const value = isControlled ? controlledValue : uncontrolledValue;

    const getPercentage = (val: number) => ((val - min) / (max - min)) * 100;

    const getValueFromPosition = useCallback(
      (clientX: number, clientY: number) => {
        if (!trackRef.current) return value[0];

        const rect = trackRef.current.getBoundingClientRect();
        let percentage: number;

        if (orientation === 'horizontal') {
          percentage = (clientX - rect.left) / rect.width;
        } else {
          percentage = 1 - (clientY - rect.top) / rect.height;
        }

        percentage = Math.max(0, Math.min(1, percentage));
        const rawValue = min + percentage * (max - min);
        const steppedValue = Math.round(rawValue / step) * step;
        return Math.max(min, Math.min(max, steppedValue));
      },
      [min, max, step, orientation, value]
    );

    const handleValueChange = useCallback(
      (newValue: number[]) => {
        if (!isControlled) {
          setUncontrolledValue(newValue);
        }
        onValueChange?.(newValue);
      },
      [isControlled, onValueChange]
    );

    const handlePointerDown = (e: React.PointerEvent) => {
      if (disabled) return;
      e.preventDefault();
      isDragging.current = true;

      const newValue = getValueFromPosition(e.clientX, e.clientY) ?? min;
      handleValueChange([newValue]);

      const handlePointerMove = (moveEvent: PointerEvent) => {
        if (!isDragging.current) return;
        const moveValue = getValueFromPosition(moveEvent.clientX, moveEvent.clientY) ?? min;
        handleValueChange([moveValue]);
      };

      const handlePointerUp = () => {
        isDragging.current = false;
        onValueCommit?.(value);
        document.removeEventListener('pointermove', handlePointerMove);
        document.removeEventListener('pointerup', handlePointerUp);
      };

      document.addEventListener('pointermove', handlePointerMove);
      document.addEventListener('pointerup', handlePointerUp);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
      if (disabled) return;

      const currentVal = value[0] ?? min;
      let newValue = currentVal;

      switch (e.key) {
        case 'ArrowLeft':
        case 'ArrowDown':
          newValue = Math.max(min, currentVal - step);
          break;
        case 'ArrowRight':
        case 'ArrowUp':
          newValue = Math.min(max, currentVal + step);
          break;
        case 'Home':
          newValue = min;
          break;
        case 'End':
          newValue = max;
          break;
        default:
          return;
      }

      e.preventDefault();
      handleValueChange([newValue]);
    };

    const isHorizontal = orientation === 'horizontal';

    return (
      <div
        ref={ref}
        className={cn(
          'relative flex touch-none select-none items-center',
          isHorizontal ? 'w-full' : 'h-full flex-col',
          disabled && 'opacity-50 cursor-not-allowed',
          className
        )}
        {...props}
      >
        <div
          ref={trackRef}
          className={cn(
            'relative grow rounded-full bg-gray-200 dark:bg-gray-700',
            isHorizontal ? 'h-2 w-full' : 'w-2 h-full'
          )}
          onPointerDown={handlePointerDown}
        >
          <div
            className={cn(
              'absolute rounded-full bg-primary-600 dark:bg-primary-500',
              isHorizontal ? 'h-full left-0' : 'w-full bottom-0'
            )}
            style={
              isHorizontal
                ? { width: `${getPercentage(value[0] ?? min)}%` }
                : { height: `${getPercentage(value[0] ?? min)}%` }
            }
          />
          <div
            role="slider"
            tabIndex={disabled ? -1 : 0}
            aria-valuemin={min}
            aria-valuemax={max}
            aria-valuenow={value[0] ?? min}
            aria-orientation={orientation}
            aria-disabled={disabled}
            className={cn(
              'absolute block h-5 w-5 rounded-full',
              'bg-white dark:bg-gray-100 border-2 border-primary-600 dark:border-primary-500',
              'shadow-md transition-colors',
              'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
              'hover:bg-gray-50 dark:hover:bg-gray-200',
              isHorizontal ? '-translate-x-1/2 -translate-y-1/2 top-1/2' : '-translate-x-1/2 translate-y-1/2 left-1/2'
            )}
            style={
              isHorizontal
                ? { left: `${getPercentage(value[0] ?? min)}%` }
                : { bottom: `${getPercentage(value[0] ?? min)}%` }
            }
            onKeyDown={handleKeyDown}
          />
        </div>
      </div>
    );
  }
);

Slider.displayName = 'Slider';

export { Slider };
