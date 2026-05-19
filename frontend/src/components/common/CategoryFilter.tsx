import {
  forwardRef,
  useCallback,
  useEffect,
  useRef,
  useState,
  type HTMLAttributes,
  type ReactNode,
} from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface CategoryFilterItem {
  /** Stable identifier. Used to control selection. */
  id: string;
  /** Display label. */
  label: string;
  /** Optional leading icon or emoji. */
  icon?: ReactNode;
  /** Optional count shown as a subtle trailing badge. */
  count?: number;
  /** Disabled state for this specific option. */
  disabled?: boolean;
}

export interface CategoryFilterProps extends Omit<HTMLAttributes<HTMLDivElement>, 'onChange'> {
  items: CategoryFilterItem[];
  /**
   * Currently selected id. `undefined` means the "all" option is active
   * (or nothing selected if `allItem` is not provided).
   */
  value?: string;
  onChange: (next: string | undefined) => void;
  /**
   * Optional pseudo-item rendered as the first pill. When active, `value` is
   * `undefined`. Pass `{ label: 'All', count: 123 }` to show a total.
   */
  allItem?: {
    label: string;
    count?: number;
    icon?: ReactNode;
  };
  /**
   * Background color the fade-mask should blend into. Defaults to
   * `background` (the PageShell/WorkPanel surface). Set to `surface` when
   * the filter sits inside a card or other elevated container.
   */
  fadeColor?: 'background' | 'surface' | 'surface-elevated' | 'surface-sunken';
  /** Accessible group label. Defaults to "Category filter". */
  'aria-label'?: string;
}

const fadeFromClass: Record<NonNullable<CategoryFilterProps['fadeColor']>, string> = {
  background: 'from-background',
  surface: 'from-surface',
  'surface-elevated': 'from-surface-elevated',
  'surface-sunken': 'from-surface-sunken',
};

/**
 * Horizontal pill-based filter strip. Hides its scrollbar and reveals soft
 * edge-fade masks + chevron scroll buttons only when content overflows —
 * matching the calm, productivity-tool feel of the design system (§3.2).
 *
 * Selection model: clicking the active pill deselects it (emits `undefined`).
 * Use `allItem` to render a leading "All" pill that maps to `undefined`.
 */
export const CategoryFilter = forwardRef<HTMLDivElement, CategoryFilterProps>(
  (
    {
      items,
      value,
      onChange,
      allItem,
      fadeColor = 'background',
      className,
      'aria-label': ariaLabel = 'Category filter',
      ...rest
    },
    ref,
  ) => {
    const scrollRef = useRef<HTMLDivElement>(null);
    const [canScrollLeft, setCanScrollLeft] = useState(false);
    const [canScrollRight, setCanScrollRight] = useState(false);

    const updateScrollState = useCallback(() => {
      const el = scrollRef.current;
      if (!el) return;
      const { scrollLeft, scrollWidth, clientWidth } = el;
      setCanScrollLeft(scrollLeft > 1);
      setCanScrollRight(scrollLeft + clientWidth < scrollWidth - 1);
    }, []);

    useEffect(() => {
      const el = scrollRef.current;
      if (!el) return;
      updateScrollState();
      el.addEventListener('scroll', updateScrollState, { passive: true });
      const ro = new ResizeObserver(updateScrollState);
      ro.observe(el);
      return () => {
        el.removeEventListener('scroll', updateScrollState);
        ro.disconnect();
      };
    }, [updateScrollState, items.length]);

    // Keep the active pill visible when selection changes programmatically.
    useEffect(() => {
      const el = scrollRef.current;
      if (!el) return;
      const key = value ?? '__all__';
      const target = el.querySelector<HTMLElement>(`[data-cf-pill="${CSS.escape(key)}"]`);
      if (!target) return;
      const elRect = el.getBoundingClientRect();
      const tRect = target.getBoundingClientRect();
      if (tRect.left < elRect.left || tRect.right > elRect.right) {
        target.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
      }
    }, [value]);

    const scrollByAmount = (delta: number) => {
      const el = scrollRef.current;
      if (!el) return;
      // Scroll by ~80% of visible width for predictable pagination feel.
      const amount = delta * Math.max(160, Math.floor(el.clientWidth * 0.8));
      el.scrollBy({ left: amount, behavior: 'smooth' });
    };

    const renderPill = (
      id: string | undefined,
      label: string,
      count: number | undefined,
      icon: ReactNode | undefined,
      disabled = false,
    ) => {
      const key = id ?? '__all__';
      const isActive = value === id;
      return (
        <button
          key={key}
          data-cf-pill={key}
          type="button"
          role="button"
          aria-pressed={isActive}
          disabled={disabled}
          onClick={() => onChange(isActive && id !== undefined ? undefined : id)}
          className={cn(
            'group inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5',
            'text-xs font-medium whitespace-nowrap',
            'transition-colors duration-200',
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 focus-visible:ring-offset-2 focus-visible:ring-offset-background',
            'disabled:cursor-not-allowed disabled:opacity-50',
            isActive
              ? 'border-primary-500/40 bg-primary-50 text-primary-700 shadow-sm dark:border-primary-400/40 dark:bg-primary-900/30 dark:text-primary-200'
              : 'border-border bg-surface text-muted-foreground hover:border-border hover:bg-surface-sunken hover:text-foreground',
          )}
        >
          {icon !== undefined && icon !== null && (
            <span className="flex items-center text-sm leading-none">{icon}</span>
          )}
          <span>{label}</span>
          {typeof count === 'number' && (
            <span
              className={cn(
                'inline-flex min-w-[1.25rem] items-center justify-center rounded-full px-1 py-px',
                'text-[10px] font-semibold leading-none tabular-nums',
                'transition-colors duration-200',
                isActive
                  ? 'bg-primary-100 text-primary-700 dark:bg-primary-400/20 dark:text-primary-100'
                  : 'bg-surface-sunken text-muted-foreground-tertiary group-hover:bg-background',
              )}
            >
              {count}
            </span>
          )}
        </button>
      );
    };

    const fromCls = fadeFromClass[fadeColor];

    return (
      <div
        ref={ref}
        role="group"
        aria-label={ariaLabel}
        className={cn('relative min-w-0 flex-1', className)}
        {...rest}
      >
        {/* Left edge fade — purely decorative, doesn't block clicks. */}
        <div
          aria-hidden
          className={cn(
            'pointer-events-none absolute inset-y-0 left-0 z-10 w-10 bg-gradient-to-r to-transparent',
            'transition-opacity duration-200',
            fromCls,
            canScrollLeft ? 'opacity-100' : 'opacity-0',
          )}
        />
        {/* Right edge fade. */}
        <div
          aria-hidden
          className={cn(
            'pointer-events-none absolute inset-y-0 right-0 z-10 w-10 bg-gradient-to-l to-transparent',
            'transition-opacity duration-200',
            fromCls,
            canScrollRight ? 'opacity-100' : 'opacity-0',
          )}
        />

        {/* Scroll affordance buttons — only interactive when overflow exists. */}
        <ScrollButton
          side="left"
          visible={canScrollLeft}
          onClick={() => scrollByAmount(-1)}
        />
        <ScrollButton
          side="right"
          visible={canScrollRight}
          onClick={() => scrollByAmount(1)}
        />

        <div
          ref={scrollRef}
          className="no-scrollbar flex items-center gap-1.5 overflow-x-auto py-0.5"
        >
          {allItem && renderPill(undefined, allItem.label, allItem.count, allItem.icon)}
          {items.map((item) =>
            renderPill(item.id, item.label, item.count, item.icon, item.disabled),
          )}
        </div>
      </div>
    );
  },
);
CategoryFilter.displayName = 'CategoryFilter';

interface ScrollButtonProps {
  side: 'left' | 'right';
  visible: boolean;
  onClick: () => void;
}

function ScrollButton({ side, visible, onClick }: ScrollButtonProps) {
  const Icon = side === 'left' ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      tabIndex={visible ? 0 : -1}
      aria-hidden={!visible}
      aria-label={side === 'left' ? 'Scroll filters left' : 'Scroll filters right'}
      onClick={onClick}
      className={cn(
        'absolute top-1/2 z-20 flex h-7 w-7 -translate-y-1/2 items-center justify-center',
        'rounded-full border border-border bg-surface/95 text-muted-foreground',
        'shadow-sm backdrop-blur-sm',
        'transition-[opacity,transform,color,border-color] duration-200',
        'hover:border-primary-300 hover:text-foreground dark:hover:border-primary-700',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50',
        side === 'left' ? 'left-1' : 'right-1',
        visible ? 'opacity-100 pointer-events-auto' : 'pointer-events-none opacity-0',
      )}
    >
      <Icon className="h-3.5 w-3.5" />
    </button>
  );
}
