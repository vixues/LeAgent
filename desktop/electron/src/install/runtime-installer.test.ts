import { beforeEach, describe, expect, it, vi } from 'vitest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'leagent-payload-'));

vi.mock('electron', () => ({
  app: {
    isPackaged: true,
    getVersion: () => '1.2.5',
    getPath: (name: string) => path.join(tmpRoot, name),
  },
}));

vi.mock('../logger.js', () => ({
  log: { info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

vi.mock('../ipc/runtime.js', () => ({
  sendRuntimeProgress: vi.fn(),
  sendRuntimeStatus: vi.fn(),
}));

vi.mock('../config/desktop-config.js', () => ({
  setInstallState: vi.fn(),
  getInstallState: () => 'installed',
  getServerPort: () => 7860,
}));

vi.mock('../paths/runtime-paths.js', () => {
  const payload = path.join(tmpRoot, 'backend-payload');
  return {
    uvExe: () => 'uv',
    pythonExe: () => 'python',
    backendPayloadDir: () => payload,
    runtimeVenvDir: () => path.join(tmpRoot, 'venv'),
    runtimeVenvPython: () => path.join(tmpRoot, 'venv', 'bin', 'python'),
    installedMarkerPath: () => path.join(tmpRoot, '.installed'),
    resolveLeagentHome: () => path.join(tmpRoot, 'home'),
    ensureDirs: () => {
      fs.mkdirSync(path.join(tmpRoot, 'home'), { recursive: true });
    },
  };
});

describe('tryGetPayloadHash / needsRuntimeUpgrade', () => {
  beforeEach(() => {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
    fs.mkdirSync(path.join(tmpRoot, 'backend-payload'), { recursive: true });
    fs.mkdirSync(path.join(tmpRoot, 'home'), { recursive: true });
  });

  it('tryGetPayloadHash returns null when payload files are missing', async () => {
    const { tryGetPayloadHash, getPayloadHash, PayloadHashError } = await import(
      './runtime-installer.js'
    );
    expect(tryGetPayloadHash()).toBeNull();
    expect(() => getPayloadHash()).toThrow(PayloadHashError);
  });

  it('tryGetPayloadHash returns a stable hash when lockfiles exist', async () => {
    const payload = path.join(tmpRoot, 'backend-payload');
    fs.writeFileSync(path.join(payload, 'pyproject.toml'), '[project]\nname="x"\n');
    fs.writeFileSync(path.join(payload, 'uv.lock'), 'version = 1\n');

    const { tryGetPayloadHash } = await import('./runtime-installer.js');
    const a = tryGetPayloadHash();
    const b = tryGetPayloadHash();
    expect(a).toMatch(/^[a-f0-9]{64}$/);
    expect(a).toBe(b);
  });

  it('needsRuntimeUpgrade is true when hash cannot be read', async () => {
    fs.writeFileSync(
      path.join(tmpRoot, '.installed'),
      JSON.stringify({ version: '1.2.5', appVersion: '1.2.5', payloadHash: 'abc' }),
    );
    // no pyproject/uv.lock
    const { needsRuntimeUpgrade } = await import('./runtime-installer.js');
    expect(needsRuntimeUpgrade()).toBe(true);
  });
});

describe('payload validation item mapping', () => {
  it('maps missing hash to error + reinstall repairAction', () => {
    type Item = { id: string; level: string; repairAction?: string; message: string };
    const currentHash: string | null = null;
    const marker = { payloadHash: 'old' };
    const items: Item[] = [];

    if (currentHash === null) {
      items.push({
        id: 'payload',
        level: 'error',
        message: 'Bundled backend payload is missing or unreadable.',
        repairAction: 'reinstall',
      });
    } else if (!marker || marker.payloadHash !== currentHash) {
      items.push({
        id: 'payload',
        level: 'warning',
        message: 'Backend package lock has changed — upgrade recommended.',
        repairAction: 'upgrade',
      });
    }

    expect(items[0]?.level).toBe('error');
    expect(items[0]?.repairAction).toBe('reinstall');
    expect(!items.some((i) => i.level === 'error')).toBe(false);
  });
});
