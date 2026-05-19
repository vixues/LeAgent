import { spawn } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { app } from 'electron';
import { log } from '../logger';
import { sendRuntimeProgress, sendRuntimeStatus } from '../ipc/runtime';
import {
  uvExe,
  pythonExe,
  backendPayloadDir,
  runtimeVenvDir,
  runtimeVenvPython,
  installedMarkerPath,
  leagentHome,
  ensureDirs,
} from './runtime-paths';

const APP_VERSION = app.getVersion();

interface InstalledMarker {
  version: string;
  timestamp: string;
  payloadHash?: string;
}

function dependencyPayloadHash(): string {
  const hash = crypto.createHash('sha256');
  const payload = backendPayloadDir();

  for (const file of ['pyproject.toml', 'uv.lock']) {
    const filePath = path.join(payload, file);
    hash.update(file);
    hash.update('\0');
    hash.update(fs.readFileSync(filePath));
    hash.update('\0');
  }

  return hash.digest('hex');
}

function readMarker(): InstalledMarker | null {
  try {
    const raw = fs.readFileSync(installedMarkerPath(), 'utf-8');
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function writeMarker(payloadHash: string): void {
  const marker: InstalledMarker = {
    version: APP_VERSION,
    payloadHash,
    timestamp: new Date().toISOString(),
  };
  fs.writeFileSync(installedMarkerPath(), JSON.stringify(marker, null, 2));
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

export async function isRuntimeReady(): Promise<boolean> {
  if (!app.isPackaged) {
    return fs.existsSync(runtimeVenvPython());
  }

  const marker = readMarker();
  if (!marker) return false;
  if (marker.version !== APP_VERSION) return false;
  if (marker.payloadHash !== dependencyPayloadHash()) return false;
  return fs.existsSync(runtimeVenvPython());
}

export async function installRuntime(): Promise<void> {
  ensureDirs();
  const uv = uvExe();
  const python = pythonExe();
  const payload = backendPayloadDir();
  const payloadHash = dependencyPayloadHash();
  const venvDir = runtimeVenvDir();
  const home = leagentHome();

  const totalSteps = 4;
  let step = 0;

  const progress = (detail: string) => {
    step++;
    const pct = Math.round((step / totalSteps) * 100);
    sendRuntimeProgress(pct, detail);
    sendRuntimeStatus(detail);
    log.info(`[install ${pct}%] ${detail}`);
  };

  // Step 1: Create venv
  progress('Creating Python virtual environment…');
  if (fs.existsSync(venvDir)) {
    fs.rmSync(venvDir, { recursive: true, force: true });
  }
  await runCommand(uv, ['venv', venvDir, '--python', python]);

  // Step 2: Install dependencies
  progress('Installing dependencies (uv sync)…');
  await runCommand(uv, ['sync', '--project', payload, '--frozen'], {
    env: {
      VIRTUAL_ENV: venvDir,
      UV_PROJECT_ENVIRONMENT: venvDir,
    },
  });

  // Step 3: Compile bytecode for faster subsequent imports
  progress('Compiling bytecode cache…');
  const venvPy = runtimeVenvPython();
  try {
    await runCommand(venvPy, ['-m', 'compileall', '-q', path.join(payload, 'leagent')]);
  } catch {
    log.warn('compileall leagent failed (non-fatal)');
  }

  // Step 4: Run database migrations
  progress('Applying database migrations…');
  try {
    await runCommand(venvPy, ['-m', 'alembic', 'upgrade', 'head'], {
      cwd: payload,
      env: {
        VIRTUAL_ENV: venvDir,
        LEAGENT_HOME: home,
      },
    });
  } catch {
    log.warn('Alembic migrations failed (non-fatal — first run may have no revisions)');
  }

  writeMarker(payloadHash);
  sendRuntimeProgress(100, 'Runtime ready');
  log.info('Runtime installation complete');
}
