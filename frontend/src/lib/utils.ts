import { type ClassValue, clsx } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

import i18n from '@/i18n';

/** Ensures semantic palette tokens from `tailwind.config.js` merge like built-in colors (e.g. `bg-surface` vs `bg-background`). */
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      colors: [
        'background',
        'foreground',
        'surface',
        'surface-elevated',
        'surface-sunken',
        'muted-foreground',
        'muted-foreground-tertiary',
        'border',
        'border-subtle',
      ],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Parse API datetime strings. DB ``timestamp`` values are UTC wall time but
 * often serialize without a zone; ECMAScript treats those as local, skewing
 * relative times by the host offset. Treat naive ``...T...`` as UTC.
 */
export function parseApiDateTime(iso: string): Date {
  const raw = iso.trim();
  if (!raw) return new Date(NaN);
  const normalized = raw.includes('T') ? raw : raw.replace(/^(\d{4}-\d{2}-\d{2})\s+/, '$1T');
  if (/Z$/i.test(normalized)) return new Date(normalized);
  if (/[+-]\d{2}:\d{2}$/.test(normalized)) return new Date(normalized);
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(normalized)) {
    return new Date(`${normalized}Z`);
  }
  return new Date(raw);
}

export function formatDate(date: Date | string, locale?: string): string {
  const d = typeof date === 'string' ? parseApiDateTime(date) : date;
  const loc = locale ?? i18n.language ?? 'zh-CN';
  return new Intl.DateTimeFormat(loc, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d);
}

export function formatRelativeTime(date: Date | string, locale?: string): string {
  const d = typeof date === 'string' ? parseApiDateTime(date) : date;
  const now = new Date();
  const diff = now.getTime() - d.getTime();

  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  const loc = locale ?? i18n.language ?? 'zh-CN';
  const rtf = new Intl.RelativeTimeFormat(loc, { numeric: 'auto' });

  if (days > 0) return rtf.format(-days, 'day');
  if (hours > 0) return rtf.format(-hours, 'hour');
  if (minutes > 0) return rtf.format(-minutes, 'minute');
  return rtf.format(-seconds, 'second');
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function debounce<T extends (...args: Parameters<T>) => void>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout>;
  return (...args: Parameters<T>) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
}

export function throttle<T extends (...args: Parameters<T>) => void>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => void {
  let lastCall = 0;
  return (...args: Parameters<T>) => {
    const now = Date.now();
    if (now - lastCall >= delay) {
      lastCall = now;
      fn(...args);
    }
  };
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(id: string | null | undefined): boolean {
  return !!id && UUID_RE.test(id);
}

export function generateId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}
