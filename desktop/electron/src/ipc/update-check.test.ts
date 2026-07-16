import { describe, expect, it } from 'vitest';
import { isRemoteNewer, toUpdateCheckResult } from './update-check.js';

describe('isRemoteNewer', () => {
  it('detects newer remote versions', () => {
    expect(isRemoteNewer('1.2.5', '1.2.6')).toBe(true);
    expect(isRemoteNewer('1.2.5', '1.3.0')).toBe(true);
    expect(isRemoteNewer('1.2.5', '2.0.0')).toBe(true);
  });

  it('returns false for equal or older remote', () => {
    expect(isRemoteNewer('1.2.5', '1.2.5')).toBe(false);
    expect(isRemoteNewer('1.2.5', '1.2.4')).toBe(false);
    expect(isRemoteNewer('1.2.5', 'v1.2.5')).toBe(false);
  });
});

describe('toUpdateCheckResult', () => {
  it('marks updateAvailable when remote is newer', () => {
    expect(toUpdateCheckResult('1.0.0', '1.1.0')).toEqual({
      ok: true,
      updateAvailable: true,
      version: '1.1.0',
    });
  });

  it('marks no update when remote missing or equal', () => {
    expect(toUpdateCheckResult('1.0.0', null)).toEqual({
      ok: true,
      updateAvailable: false,
    });
    expect(toUpdateCheckResult('1.0.0', '1.0.0')).toEqual({
      ok: true,
      updateAvailable: false,
      version: '1.0.0',
    });
  });

  it('matches AboutDialog branching: ok+updateAvailable vs ok+none vs !ok', () => {
    const pickMsg = (r: ReturnType<typeof toUpdateCheckResult> & { message?: string }) => {
      if (!r.ok) return 'error';
      if (r.updateAvailable) return 'available';
      return 'none';
    };
    expect(pickMsg(toUpdateCheckResult('1.2.5', '1.2.6'))).toBe('available');
    expect(pickMsg(toUpdateCheckResult('1.2.5', '1.2.5'))).toBe('none');
    expect(pickMsg({ ok: false, updateAvailable: false, message: 'net' })).toBe('error');
  });
});
