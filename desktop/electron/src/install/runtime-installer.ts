import { spawn } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { app } from 'electron';
import { log } from '../logger.js';
import { sendRuntimeProgress, sendRuntimeStatus } from '../ipc/runtime.js';
import { setInstallState } from '../config/desktop-config.js';
import {
  uvExe,
  pythonExe,
  backendPayloadDir,
  runtimeVenvDir,
  runtimeVenvPython,
  installedMarkerPath,
  resolveLeagentHome,
  ensureDirs,
} from '../paths/runtime-paths.js';

const APP_VERSION = app.getVersion();

export interface InstalledMarker {
  version: string;
  timestamp: string;
  payloadHash?: string;
  appVersion?: string;
}

export class PayloadHashError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PayloadHashError';
  }
}

function dependencyPayloadHash(): string {
  const hash = crypto.createHash('sha256');
  const payload = backendPayloadDir();

  for (const file of ['pyproject.toml', 'uv.lock']) {
    const filePath = path.join(payload, file);
    try {
      hash.update(file);
      hash.update('\0');
      hash.update(fs.readFileSync(filePath));
      hash.update('\0');
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : String(err);
      throw new PayloadHashError(`Cannot read backend payload file ${file}: ${detail}`);
    }
  }

  return hash.digest('hex');
}

export function readInstalledMarker(): InstalledMarker | null {
  try {
    const raw = fs.readFileSync(installedMarkerPath(), 'utf-8');
    return JSON.parse(raw) as InstalledMarker;
  } catch {
    return null;
  }
}

function writeMarker(payloadHash: string): void {
  const marker: InstalledMarker = {
    version: APP_VERSION,
    appVersion: APP_VERSION,
    payloadHash,
    timestamp: new Date().toISOString(),
  };
  fs.writeFileSync(installedMarkerPath(), JSON.stringify(marker, null, 2));
  setInstallState('installed');
}

function runCommand(
  cmd: string,
  args: string[],
  opts: { cwd?: string; env?: NodeJS.ProcessEnv } = {},
): Promise<void> {
  return new Promise((resolve, reject) => {
    log.info(`> ${cmd} ${args.join(' ')}`);
    const child = spawn(cmd, args, {
      cwd: opts.cwd,
      env: { ...process.env, ...opts.env },
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });

    child.stdout?.on('data', (data: Buffer) => {
      const line = data.toString().trim();
      if (line) {
        log.info(`[runtime] ${line}`);
        sendRuntimeStatus(line);
      }
    });

    child.stderr?.on('data', (data: Buffer) => {
      const line = data.toString().trim();
      if (line) {
        log.warn(`[runtime] ${line}`);
      }
    });

    child.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${cmd} exited with code ${code}`));
    });

    child.on('error', reject);
  });
}

export function getPayloadHash(): string {
  return dependencyPayloadHash();
}

/** Safe hash read for validation — returns null when payload files are missing/unreadable. */
export function tryGetPayloadHash(): string | null {
  try {
    return dependencyPayloadHash();
  } catch {
    return null;
  }
}

export function needsRuntimeUpgrade(): boolean {
  if (!app.isPackaged) return false;
  const marker = readInstalledMarker();
  if (!marker) return true;
  if (marker.appVersion !== APP_VERSION || marker.version !== APP_VERSION) return true;
  try {
    if (marker.payloadHash !== dependencyPayloadHash()) return true;
  } catch {
    return true;
  }
  return !fs.existsSync(runtimeVenvPython());
}

export async function isRuntimeReady(): Promise<boolean> {
  if (!app.isPackaged) {
    return fs.existsSync(runtimeVenvPython());
  }
  return !needsRuntimeUpgrade();
}

export async function installRuntime(fresh = true): Promise<void> {
  ensureDirs();
  setInstallState('started');
  const uv = uvExe();
  const python = pythonExe();
  const payload = backendPayloadDir();
  const payloadHash = dependencyPayloadHash();
  const venvDir = runtimeVenvDir();
  const home = resolveLeagentHome();

  const totalSteps = 4;
  let step = 0;

  const progress = (detail: string) => {
    step++;
    const pct = Math.round((step / totalSteps) * 100);
    sendRuntimeProgress(pct, detail);
    sendRuntimeStatus(detail);
    log.info(`[install ${pct}%] ${detail}`);
  };

  if (fresh && fs.existsSync(venvDir)) {
    fs.rmSync(venvDir, { recursive: true, force: true });
  }

  if (!fs.existsSync(runtimeVenvPython())) {
    progress('Creating Python virtual environment…');
    await runCommand(uv, ['venv', venvDir, '--python', python]);
  }

  progress('Installing dependencies (uv sync)…');
  await runCommand(uv, ['sync', '--project', payload, '--frozen'], {
    env: {
      VIRTUAL_ENV: venvDir,
      UV_PROJECT_ENVIRONMENT: venvDir,
    },
  });

  progress('Compiling bytecode cache…');
  const venvPy = runtimeVenvPython();
  await runCommand(venvPy, ['-m', 'compileall', '-q', path.join(payload, 'leagent')]);

  progress('Applying database migrations…');
  await runCommand(venvPy, ['-m', 'alembic', 'upgrade', 'head'], {
    cwd: payload,
    env: {
      VIRTUAL_ENV: venvDir,
      LEAGENT_HOME: home,
    },
  });

  writeMarker(payloadHash);
  sendRuntimeProgress(100, 'Runtime ready');
  log.info('Runtime installation complete');
}

export async function upgradeRuntimePackages(): Promise<void> {
  await installRuntime(false);
}

export async function runAlembicUpgrade(): Promise<void> {
  const venvPy = runtimeVenvPython();
  const payload = backendPayloadDir();
  await runCommand(venvPy, ['-m', 'alembic', 'upgrade', 'head'], {
    cwd: payload,
    env: {
      VIRTUAL_ENV: runtimeVenvDir(),
      LEAGENT_HOME: resolveLeagentHome(),
    },
  });
}
