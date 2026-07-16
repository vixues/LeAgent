import { describe, expect, it, vi } from 'vitest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

vi.mock('electron', () => ({
  app: {
    isPackaged: false,
    getPath: (name: string) => (name === 'exe' ? '/opt/LeAgent/leagent' : `/tmp/${name}`),
  },
}));

const { isCloudSyncedPath, isDirectoryWritable, isPathInside, isInsideAppInstallDir } =
  await import('./path-handlers.js');

describe('path-handlers', () => {
  it('detects OneDrive paths', () => {
    expect(isCloudSyncedPath('/Users/me/OneDrive/Documents')).toBe(true);
    expect(isCloudSyncedPath('/home/user/projects/leagent')).toBe(false);
  });

  it('checks directory writability', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'leagent-test-'));
    expect(isDirectoryWritable(dir)).toBe(true);
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it('isPathInside checks containment', () => {
    const root = '/home/user/data';
    expect(isPathInside(root, '/home/user/data/logs/a.log')).toBe(true);
    expect(isPathInside(root, '/home/user/data')).toBe(true);
    expect(isPathInside(root, '/home/user/other')).toBe(false);
    expect(isPathInside(root, '/home/user/data-evil')).toBe(false);
  });

  it('isInsideAppInstallDir uses exe dirname in unpackaged mode', () => {
    expect(isInsideAppInstallDir('/opt/LeAgent/leagent-home')).toBe(true);
    expect(isInsideAppInstallDir('/home/user/data')).toBe(false);
  });
});
