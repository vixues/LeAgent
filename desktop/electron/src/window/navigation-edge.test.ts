import { describe, expect, it } from 'vitest';
import { isAllowedNavigationUrl } from './navigation.js';

describe('isAllowedNavigationUrl (edge cases)', () => {
  it('allows https localhost and custom ports', () => {
    expect(isAllowedNavigationUrl('https://127.0.0.1:8443/api/v1')).toBe(true);
    expect(isAllowedNavigationUrl('http://localhost:9000/')).toBe(true);
  });

  it('blocks javascript and data schemes', () => {
    expect(isAllowedNavigationUrl('javascript:alert(1)')).toBe(false);
    expect(isAllowedNavigationUrl('data:text/html,hi')).toBe(false);
  });

  it('blocks empty / invalid URLs', () => {
    expect(isAllowedNavigationUrl('')).toBe(false);
    expect(isAllowedNavigationUrl('not-a-url')).toBe(false);
  });
});
