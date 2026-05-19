import { forwardRef, useState, useMemo, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';
import { PRIMARY_SOFT_CTA_CLASSNAME } from '@/components/ui/Button';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface CalendarProps extends Omit<HTMLAttributes<HTMLDivElement>, 'onSelect'> {
  selected?: Date;
  onSelect?: (date: Date | undefined) => void;
  disabled?: (date: Date) => boolean;
  locale?: string;
  weekStartsOn?: 0 | 1 | 2 | 3 | 4 | 5 | 6;
  showOutsideDays?: boolean;
  mode?: 'single' | 'multiple' | 'range';
  minDate?: Date;
  maxDate?: Date;
}

const Calendar = forwardRef<HTMLDivElement, CalendarProps>(
  (
    {
      className,
      selected,
      onSelect,
      disabled,
      locale = 'zh-CN',
      weekStartsOn = 1,
      showOutsideDays = true,
      minDate,
      maxDate,
      ...props
    },
    ref
  ) => {
    const { t } = useTranslation();
    const [viewDate, setViewDate] = useState(() => selected || new Date());

    const weekDays = useMemo(() => {
      const result: string[] = [];
      for (let i = 0; i < 7; i++) {
        const idx = (weekStartsOn + i) % 7;
        result.push(t(`common.calendarWeekday.${idx}`));
      }
      return result;
    }, [weekStartsOn, t]);

    const monthDays = useMemo(() => {
      const year = viewDate.getFullYear();
      const month = viewDate.getMonth();

      const firstDay = new Date(year, month, 1);
      const lastDay = new Date(year, month + 1, 0);

      const firstDayOfWeek = firstDay.getDay();
      const daysToShowBefore = (firstDayOfWeek - weekStartsOn + 7) % 7;

      const days: Array<{ date: Date; isCurrentMonth: boolean }> = [];

      for (let i = daysToShowBefore - 1; i >= 0; i--) {
        const date = new Date(year, month, -i);
        days.push({ date, isCurrentMonth: false });
      }

      for (let i = 1; i <= lastDay.getDate(); i++) {
        const date = new Date(year, month, i);
        days.push({ date, isCurrentMonth: true });
      }

      const totalDays = 42;
      const remainingDays = totalDays - days.length;
      for (let i = 1; i <= remainingDays; i++) {
        const date = new Date(year, month + 1, i);
        days.push({ date, isCurrentMonth: false });
      }

      return days;
    }, [viewDate, weekStartsOn]);

    const goToPreviousMonth = () => {
      setViewDate((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
    };

    const goToNextMonth = () => {
      setViewDate((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));
    };

    const goToToday = () => {
      const today = new Date();
      setViewDate(today);
      onSelect?.(today);
    };

    const isDateDisabled = (date: Date) => {
      if (disabled?.(date)) return true;
      if (minDate && date < minDate) return true;
      if (maxDate && date > maxDate) return true;
      return false;
    };

    const isDateSelected = (date: Date) => {
      if (!selected) return false;
      return (
        date.getFullYear() === selected.getFullYear() &&
        date.getMonth() === selected.getMonth() &&
        date.getDate() === selected.getDate()
      );
    };

    const isToday = (date: Date) => {
      const today = new Date();
      return (
        date.getFullYear() === today.getFullYear() &&
        date.getMonth() === today.getMonth() &&
        date.getDate() === today.getDate()
      );
    };

    const monthFormatter = new Intl.DateTimeFormat(locale, { year: 'numeric', month: 'long' });

    return (
      <div
        ref={ref}
        className={cn(
          'p-3 bg-surface rounded-lg',
          'border border-gray-200 dark:border-gray-700',
          className
        )}
        {...props}
      >
        <div className="flex items-center justify-between mb-4">
          <button
            type="button"
            onClick={goToPreviousMonth}
            className={cn(
              'p-1.5 rounded-lg',
              'text-gray-600 dark:text-gray-400',
              'hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors'
            )}
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-gray-900 dark:text-white">
              {monthFormatter.format(viewDate)}
            </span>
            <button
              type="button"
              onClick={goToToday}
              className={cn(
                'px-2 py-0.5 text-xs rounded-md',
                'text-primary-600 dark:text-primary-400',
                'hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors'
              )}
            >
              {t('common.today')}
            </button>
          </div>
          <button
            type="button"
            onClick={goToNextMonth}
            className={cn(
              'p-1.5 rounded-lg',
              'text-gray-600 dark:text-gray-400',
              'hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors'
            )}
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </div>

        <div className="grid grid-cols-7 gap-1 mb-2">
          {weekDays.map((day, index) => (
            <div
              key={index}
              className="text-center text-xs font-medium text-gray-500 dark:text-gray-400 py-1"
            >
              {day}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-7 gap-1">
          {monthDays.map(({ date, isCurrentMonth }, index) => {
            const isDisabled = isDateDisabled(date);
            const isSelected = isDateSelected(date);
            const isTodayDate = isToday(date);

            if (!showOutsideDays && !isCurrentMonth) {
              return <div key={index} className="h-8" />;
            }

            return (
              <button
                key={index}
                type="button"
                disabled={isDisabled}
                onClick={() => !isDisabled && onSelect?.(date)}
                className={cn(
                  'h-8 w-8 mx-auto flex items-center justify-center rounded-lg text-sm',
                  'transition-colors',
                  isCurrentMonth
                    ? 'text-gray-900 dark:text-white'
                    : 'text-gray-400 dark:text-gray-600',
                  !isDisabled && !isSelected && 'hover:bg-gray-100 dark:hover:bg-gray-800',
                  isSelected && PRIMARY_SOFT_CTA_CLASSNAME,
                  isTodayDate && !isSelected && 'ring-1 ring-primary-500',
                  isDisabled && 'opacity-50 cursor-not-allowed'
                )}
              >
                {date.getDate()}
              </button>
            );
          })}
        </div>
      </div>
    );
  }
);

Calendar.displayName = 'Calendar';

export { Calendar };
