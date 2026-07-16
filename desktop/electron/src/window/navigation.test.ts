import { describe, expect, it } from 'vitest';
import { isAllowedNavigationUrl } from '../window/navigation.js';

describe('isAllowedNavigationUrl', () => {
  it('allows localhost and file URLs', () => {
    expect(isAllowedNavigationUrl('http://127.0.0.1:7860/')).toBe(true);
    expect(isAllowedNavigationUrl('http://localhost:5173/')).toBe(true);
    expect(isAllowedNavigationUrl('file:///tmp/maintenance/index.html')).toBe(true);
  });

  it('blocks external hosts', () => {
    expect(isAllowedNavigationUrl('https://evil.example/')).toBe(false);
    expect(isAllowedNavigationUrl('http://192.168.1.1/')).toBe(false);
  });
});
