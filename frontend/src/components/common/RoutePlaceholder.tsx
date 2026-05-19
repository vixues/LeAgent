import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

/**
 * RoutePlaceholder — skeleton shown while a lazy route chunk loads.
 *
 * Keep it visually similar to the `<PageShell>` container: same `max-w-7xl`
 * cap, same vertical gap (`gap-8`), so the moment the real page renders,
 * nothing shifts. We intentionally avoid any spinner that flashes on <100ms
 * loads and rely on subtle skeleton blocks instead.
 *
 * The skeleton blocks use `animate-pulse` (already in Tailwind) and the
 * design-system's `surface-sunken` token for the background, so they match
 * every theme without hand-coded colors.
 */
export function RoutePlaceholder({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      aria-label={t('common.routeLoading')}
      aria-live="polite"
      className={cn(
        'flex flex-1 flex-col gap-8',
        'mx-auto w-full max-w-7xl',
        'animate-pulse',
        className
      )}
    >
      <div className="flex flex-col gap-3">
        <div className="h-8 w-56 rounded-lg bg-surface-sunken" />
        <div className="h-4 w-80 max-w-full rounded-md bg-surface-sunken/70" />
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="h-32 rounded-xl bg-surface-sunken/60"
            aria-hidden
          />
        ))}
      </div>

      <span className="sr-only">{t('common.loading')}</span>
    </div>
  );
}

export default RoutePlaceholder;
