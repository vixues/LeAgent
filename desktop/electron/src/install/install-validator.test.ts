import { describe, expect, it } from 'vitest';
import type { ValidationItem } from '../install/install-validator.js';

function summarize(items: ValidationItem[]): boolean {
  return !items.some((i) => i.level === 'error');
}

describe('validation summary', () => {
  it('passes when no errors', () => {
    const items: ValidationItem[] = [
      { id: 'a', label: 'A', level: 'pass', message: 'ok' },
      { id: 'b', label: 'B', level: 'warning', message: 'warn' },
    ];
    expect(summarize(items)).toBe(true);
  });

  it('fails when any error', () => {
    const items: ValidationItem[] = [
      { id: 'a', label: 'A', level: 'error', message: 'bad' },
    ];
    expect(summarize(items)).toBe(false);
  });
});
