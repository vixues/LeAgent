import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const LOCALES_ROOT = join(__dirname, '..', 'locales');

function flattenKeys(obj: unknown, prefix = ''): string[] {
  if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) {
    return prefix ? [prefix] : [];
  }
  const keys: string[] = [];
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    const p = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
      keys.push(...flattenKeys(v, p));
    } else {
      keys.push(p);
    }
  }
  return keys.sort();
}

describe('i18n locale parity', () => {
  const bundles = readdirSync(join(LOCALES_ROOT, 'zh-CN'))
    .filter((f) => f.endsWith('.json'))
    .sort();

  it.each(bundles)('%s has identical key paths in zh-CN and en-US', (file) => {
    const zh = JSON.parse(readFileSync(join(LOCALES_ROOT, 'zh-CN', file), 'utf8')) as unknown;
    const en = JSON.parse(readFileSync(join(LOCALES_ROOT, 'en-US', file), 'utf8')) as unknown;
    expect(flattenKeys(en)).toEqual(flattenKeys(zh));
  });
});
