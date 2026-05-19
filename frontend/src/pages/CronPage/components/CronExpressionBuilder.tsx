import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Calendar, Clock, ChevronDown } from 'lucide-react';
import { Input } from '@/components/ui';
import { usePreviewNextRuns } from '@/controllers/API/queries/cron';

interface CronExpressionBuilderProps {
  value: string;
  onChange: (expr: string) => void;
  className?: string;
}

const PRESET_OPTIONS: { id: string; value: string }[] = [
  { id: 'presetEveryMinute', value: '* * * * *' },
  { id: 'presetEvery5m', value: '*/5 * * * *' },
  { id: 'presetEvery15m', value: '*/15 * * * *' },
  { id: 'presetEvery30m', value: '*/30 * * * *' },
  { id: 'presetHourly', value: '0 * * * *' },
  { id: 'presetEvery6h', value: '0 */6 * * *' },
  { id: 'presetDailyMidnight', value: '0 0 * * *' },
  { id: 'presetDaily3am', value: '0 3 * * *' },
  { id: 'presetDaily9am', value: '0 9 * * *' },
  { id: 'presetWeeklySun', value: '0 0 * * 0' },
  { id: 'presetWeeklyMon', value: '0 0 * * 1' },
  { id: 'presetMonthly1', value: '0 0 1 * *' },
  { id: 'presetMonthlyLast', value: '0 0 28 * *' },
  { id: 'presetYearlyJan1', value: '0 0 1 1 *' },
];

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function CronExpressionBuilder({
  value,
  onChange,
  className,
}: CronExpressionBuilderProps) {
  const { t } = useTranslation();
  const [showPresets, setShowPresets] = useState(false);
  const parts = value.split(' ');
  const isValid = parts.length >= 5;

  const { data: previewData } = usePreviewNextRuns(value, 5, {
    enabled: isValid,
  });

  const fields = useMemo(
    () => [
      { label: t('cron.builder.fieldMinute'), placeholder: t('cron.builder.phMinute'), index: 0 },
      { label: t('cron.builder.fieldHour'), placeholder: t('cron.builder.phHour'), index: 1 },
      { label: t('cron.builder.fieldDay'), placeholder: t('cron.builder.phDay'), index: 2 },
      { label: t('cron.builder.fieldMonth'), placeholder: t('cron.builder.phMonth'), index: 3 },
      { label: t('cron.builder.fieldWeekday'), placeholder: t('cron.builder.phWeekday'), index: 4 },
    ],
    [t]
  );

  const handlePartChange = (index: number, newValue: string) => {
    const newParts = [...parts];
    while (newParts.length < 5) newParts.push('*');
    newParts[index] = newValue || '*';
    onChange(newParts.slice(0, 5).join(' '));
  };

  return (
    <div className={cn('space-y-3', className)}>
      <div>
        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
          {t('cron.builder.expressionLabel')}
        </label>
        <div className="flex gap-2">
          <Input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={t('cron.modal.cronPlaceholder')}
            className={cn('flex-1 font-mono', !isValid && value && 'border-red-400')}
          />
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowPresets(!showPresets)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg',
                'border border-gray-300 dark:border-gray-600',
                'bg-surface',
                'text-gray-700 dark:text-gray-300',
                'hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors'
              )}
            >
              <Calendar className="w-4 h-4" />
              {t('cron.builder.presets')}
              <ChevronDown className="w-3 h-3" />
            </button>
            {showPresets && (
              <div className="absolute right-0 top-full mt-1 z-50 w-56 bg-surface rounded-lg border border-gray-200 dark:border-gray-700 shadow-lg py-1 max-h-64 overflow-y-auto">
                {PRESET_OPTIONS.map((preset) => (
                  <button
                    key={preset.value}
                    type="button"
                    onClick={() => {
                      onChange(preset.value);
                      setShowPresets(false);
                    }}
                    className={cn(
                      'w-full text-left px-3 py-2 text-sm',
                      'hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors',
                      value === preset.value && 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
                    )}
                  >
                    <div className="font-medium">{t(`cron.builder.${preset.id}`)}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">{preset.value}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
        {fields.map((field) => (
          <div key={field.index}>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1 text-center">
              {field.label}
            </label>
            <Input
              type="text"
              value={parts[field.index] || '*'}
              onChange={(e) => handlePartChange(field.index, e.target.value)}
              placeholder={field.placeholder}
              className="font-mono text-center text-xs"
            />
          </div>
        ))}
      </div>

      {previewData && previewData.next_runs.length > 0 && (
        <div className="rounded-lg bg-gray-50 dark:bg-surface/50 border border-gray-200 dark:border-gray-700 p-3">
          <div className="flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
            <Clock className="w-3.5 h-3.5" />
            {t('cron.builder.nextPreview')}
          </div>
          <div className="space-y-1">
            {previewData.next_runs.map((run, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400 text-xs flex items-center justify-center font-bold">
                  {i + 1}
                </span>
                <span className="text-xs text-gray-700 dark:text-gray-300 font-mono">
                  {formatDate(run)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
