import { describe, it, expect } from 'vitest';
import { normalizeLocalFolderPathForGrant } from './localFolderPath';

describe('normalizeLocalFolderPathForGrant', () => {
  it('trims whitespace', () => {
    expect(normalizeLocalFolderPathForGrant('  /home/x  ')).toBe('/home/x');
  });

  it('prefers a path-looking line in multiline clipboard', () => {
    expect(
      normalizeLocalFolderPathForGrant('From readme:\n/home/y\nfooter'),
    ).toBe('/home/y');
    expect(normalizeLocalFolderPathForGrant('\n\n/home/y\n')).toBe('/home/y');
  });

  it('strips matching quotes', () => {
    expect(normalizeLocalFolderPathForGrant('"/home/z"')).toBe('/home/z');
    expect(normalizeLocalFolderPathForGrant("'/tmp/a'")).toBe('/tmp/a');
  });

  it('parses file URLs', () => {
    expect(normalizeLocalFolderPathForGrant('file:///home/user/docs')).toBe(
      '/home/user/docs',
    );
    expect(normalizeLocalFolderPathForGrant('file:///home/a%20b')).toBe('/home/a b');
  });

  it('returns empty for empty input', () => {
    expect(normalizeLocalFolderPathForGrant('')).toBe('');
    expect(normalizeLocalFolderPathForGrant('  \n  \t  ')).toBe('');
  });
});
