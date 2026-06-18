import { describe, expect, it } from 'vitest';
import { isCloudSyncedPath, isDirectoryWritable } from '../install/path-handlers.js';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

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
});
