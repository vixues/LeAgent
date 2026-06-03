import { Card } from '@/components/ui';
import { cn, parseApiDateTime } from '@/lib/utils';

export function formatCompactNumber(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '0';
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
  if (n < 1_000_000_000) return `${(n / 1_000_000).toFixed(n < 10_000_000 ? 1 : 0)}M`;
  return `${(n / 1_000_000_000).toFixed(1)}B`;
}

export function formatUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '$0.00';
  if (n < 0.01) return `$${n.toFixed(4)}`;
  if (n < 1) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(2)}`;
}

export function formatRelativeTime(
  iso: string | null | undefined,
  t: (k: string, p?: Record<string, unknown>) => string,
): string {
  if (!iso) return t('admin.provider.neverUsed');
  const now = Date.now();
  const then = parseApiDateTime(iso).getTime();
  const diffSec = Math.max(0, Math.floor((now - then) / 1000));
  if (diffSec < 60) return t('admin.provider.justNow');
  if (diffSec < 3600) return t('admin.provider.minutesAgo', { n: Math.floor(diffSec / 60) });
  if (diffSec < 86_400) return t('admin.provider.hoursAgo', { n: Math.floor(diffSec / 3600) });
  const days = Math.floor(diffSec / 86_400);
  return t('admin.provider.daysAgo', { n: days });
}

export function truncateModelName(name: string, max = 24): string {
  if (name.length <= max) return name;
  return `${name.slice(0, max - 1)}…`;
}

/** Format latency for tables and KPIs (ms precision for sub-second). */
export function formatLatencyMs(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms) || ms <= 0) return '—';
  const rounded = Math.round(ms);
  if (rounded < 1000) return `${rounded.toLocaleString()} ms`;
  if (rounded < 60_000) return `${(rounded / 1000).toFixed(1)} s`;
  return `${(rounded / 60_000).toFixed(1)} min`;
}

/** Compact axis tick for latency (always ms for chart consistency). */
export function formatLatencyAxisTick(ms: number): string {
  if (!Number.isFinite(ms)) return '0';
  if (ms >= 1000) return `${Math.round(ms / 1000)}k`;
  return String(Math.round(ms));
}

interface StatCardProps {
  label: string;
  value: string | number;
  hint?: string;
  icon: React.ReactNode;
  accent?: string;
}

export function StatCard({
  label,
  value,
  hint,
  icon,
  accent = 'text-primary-600 dark:text-primary-400',
}: StatCardProps) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            {label}
          </p>
          <p className="mt-1 text-2xl font-semibold text-gray-900 dark:text-white truncate">
            {value}
          </p>
          {hint && (
            <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400 truncate">{hint}</p>
          )}
        </div>
        <div
          className={cn(
            'w-10 h-10 rounded-xl flex items-center justify-center bg-gray-50 dark:bg-surface-elevated',
            accent,
          )}
        >
          {icon}
        </div>
      </div>
    </Card>
  );
}
