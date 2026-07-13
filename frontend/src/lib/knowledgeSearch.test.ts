import { describe, expect, it } from 'vitest';
import {
  commitKnowledgeSearchQuery,
  normalizeKnowledgeQuery,
  shouldAutoSearch,
  shouldForceSearch,
} from '@/lib/knowledgeSearch';

describe('knowledgeSearch policy', () => {
  it('normalizes whitespace', () => {
    expect(normalizeKnowledgeQuery('  foo   bar  ')).toBe('foo bar');
  });

  it('gates auto-search for short Latin queries', () => {
    expect(shouldAutoSearch('')).toBe(false);
    expect(shouldAutoSearch('a')).toBe(false);
    expect(shouldAutoSearch('ab')).toBe(true);
    expect(shouldAutoSearch(' a ')).toBe(false);
  });

  it('allows single CJK/kana/hangul for auto-search', () => {
    expect(shouldAutoSearch('中')).toBe(true);
    expect(shouldAutoSearch('あ')).toBe(true);
    expect(shouldAutoSearch('한')).toBe(true);
  });

  it('force-search accepts any non-empty query', () => {
    expect(shouldForceSearch('a')).toBe(true);
    expect(shouldForceSearch('  ')).toBe(false);
  });

  it('commit respects force vs auto gates', () => {
    expect(commitKnowledgeSearchQuery('a')).toBe('');
    expect(commitKnowledgeSearchQuery('a', { force: true })).toBe('a');
    expect(commitKnowledgeSearchQuery('agent')).toBe('agent');
    expect(commitKnowledgeSearchQuery('中')).toBe('中');
    expect(commitKnowledgeSearchQuery('  ')).toBe('');
  });
});
