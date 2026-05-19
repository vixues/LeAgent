import { spawn, type ChildProcess } from 'node:child_process';
import path from 'node:path';
import { app } from 'electron';
import { log } from '../logger';
import { sendRuntimeStatus } from '../ipc/runtime';
import {
  runtimeVenvPython,
  backendWorkingDir,
  leagentHome,
  frontendDir,
  runtimeVenvDir,
  runtimeVenvBinDir,
} from './runtime-paths';

const BACKEND_PORT = 7860;
const HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/health`;
const FRONTEND_URL = `http://127.0.0.1:${BACKEND_PORT}/`;
const MAX_HEALTH_ATTEMPTS = 240; // 120s max with backoff
const MAX_FRONTEND_ATTEMPTS = 120; // backend warmup can mount the SPA after /health passes

let backendProcess: ChildProcess | null = null;
let shuttingDown = false;
let backendExit: { code: number | null; signal: NodeJS.Signals | null } | null = null;

export function getBackendPort(): number {
  return BACKEND_PORT;
}

export async function startBackend(): Promise<void> {
  if (backendProcess) {
    log.warn('Backend already running');
    return;
  }

  shuttingDown = false;
  backendExit = null;
  const python = runtimeVenvPython();
  const backendDir = backendWorkingDir();
  const home = leagentHome();
  const frontend = frontendDir();
  const venvBin = runtimeVenvBinDir();

  const args = [
    '-m', 'leagent.server',
    '--host', '127.0.0.1',
    '--port', String(BACKEND_PORT),
  ];

  const env: NodeJS.ProcessEnv = {
    ...process.env,
    VIRTUAL_ENV: runtimeVenvDir(),
    UV_PROJECT_ENVIRONMENT: runtimeVenvDir(),
    LEAGENT_HOME: home,
    LEAGENT_DESKTOP: '1',
    ...(app.isPackaged ? { LEAGENT_FRONTEND_DIST: frontend } : {}),
    PYTHONDONTWRITEBYTECODE: '0',
    PYTHONUNBUFFERED: '1',
    PATH: `${venvBin}${path.delimiter}${process.env.PATH ?? ''}`,
  };

  log.info(`Starting backend: ${python} ${args.join(' ')}`);
  sendRuntimeStatus('Starting backend server…');

  backendProcess = spawn(python, args, {
    cwd: backendDir,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });

  backendProcess.stdout?.on('data', (data: Buffer) => {
    log.info(`[backend] ${data.toString().trim()}`);
  });

  backendProcess.stderr?.on('data', (data: Buffer) => {
    log.warn(`[backend] ${data.toString().trim()}`);
  });

  backendProcess.on('close', (code, signal) => {
    backendExit = { code, signal };
    log.info(`Backend exited with code ${code}${signal ? ` signal ${signal}` : ''}`);
    backendProcess = null;
    if (!shuttingDown && code !== 0) {
      log.warn('Backend crashed — restarting in 2s…');
      sendRuntimeStatus('Backend crashed — restarting…');
      setTimeout(() => {
        if (!shuttingDown) startBackend();
      }, 2000);
    }
  });

  backendProcess.on('error', (err) => {
    log.error('Backend spawn error:', err);
    backendProcess = null;
  });
}

export async function waitForHealth(): Promise<void> {
  sendRuntimeStatus('Waiting for backend health check…');
  let delay = 50;

  for (let i = 0; i < MAX_HEALTH_ATTEMPTS; i++) {
    if (backendExit) {
      const reason =
        backendExit.signal ? `signal ${backendExit.signal}` : `code ${backendExit.code}`;
      throw new Error(`Backend exited before becoming healthy (${reason})`);
    }

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 2000);
      const res = await fetch(HEALTH_URL, { signal: controller.signal });
      clearTimeout(timeout);
      if (res.ok) {
        log.info('Backend health check passed');
        sendRuntimeStatus('Backend ready');
        return;
      }
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(delay * 1.5, 1000);
  }

  throw new Error(`Backend did not become healthy after ${MAX_HEALTH_ATTEMPTS} attempts`);
}

export async function waitForFrontendReady(): Promise<void> {
  sendRuntimeStatus('Loading frontend…');
  let delay = 100;

  for (let i = 0; i < MAX_FRONTEND_ATTEMPTS; i++) {
    if (backendExit) {
      const reason =
        backendExit.signal ? `signal ${backendExit.signal}` : `code ${backendExit.code}`;
      throw new Error(`Backend exited before frontend was ready (${reason})`);
    }

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 2000);
      try {
        const res = await fetch(FRONTEND_URL, { signal: controller.signal });
        const contentType = res.headers.get('content-type') ?? '';
        if (res.ok && contentType.includes('text/html')) {
          const body = await res.text();
          if (body.includes('<!doctype html') || body.includes('<div id="root"')) {
            log.info('Frontend SPA is ready');
            sendRuntimeStatus('Frontend ready');
            return;
          }
        }
      } finally {
        clearTimeout(timeout);
      }
    } catch {
      // not ready yet
    }

    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(delay * 1.4, 1000);
  }

  throw new Error(`Frontend did not become ready after ${MAX_FRONTEND_ATTEMPTS} attempts`);
}

export function stopBackend(): void {
  shuttingDown = true;
  if (!backendProcess) return;
  log.info('Stopping backend…');
  if (process.platform === 'win32') {
    backendProcess.kill();
  } else {
    backendProcess.kill('SIGTERM');
    setTimeout(() => {
      if (backendProcess && !backendProcess.killed) {
        backendProcess.kill('SIGKILL');
      }
    }, 5000);
  }
}

export function isBackendRunning(): boolean {
  return backendProcess !== null && !backendProcess.killed;
}
