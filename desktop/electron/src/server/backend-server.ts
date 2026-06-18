import { spawn, type ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { app, type BrowserWindow } from 'electron';
import {
  BACKEND_KILL_TIMEOUT_MS,
  FRONTEND_MAX_ATTEMPTS,
  HEALTH_MAX_ATTEMPTS,
  IPC,
  MAX_BACKEND_RESTARTS,
} from '../constants.js';
import { getServerPort } from '../config/desktop-config.js';
import { createFileLogger, log as mainLog } from '../logger.js';
import { sendRuntimeStatus } from '../ipc/runtime.js';
import {
  backendLogPath,
  backendWorkingDir,
  frontendDir,
  resolveLeagentHome,
  runtimeVenvBinDir,
  runtimeVenvDir,
  runtimeVenvPython,
} from '../paths/runtime-paths.js';

const backendFileLog = createFileLogger('backend', 'backend.log');

const LOG_RING_MAX = 200;
const logRing: string[] = [];

function appendLogLine(line: string): void {
  logRing.push(line);
  if (logRing.length > LOG_RING_MAX) logRing.shift();
}

function broadcastLog(windows: BrowserWindow[], line: string): void {
  for (const win of windows) {
    if (!win.isDestroyed()) {
      win.webContents.send(IPC.SERVER_LOG, line);
    }
  }
}

export type ServerStatus = 'stopped' | 'starting' | 'running' | 'crashed' | 'failed';

export class BackendServer {
  private process: ChildProcess | null = null;
  private shuttingDown = false;
  private crashCount = 0;
  private status: ServerStatus = 'stopped';
  private backendExit: { code: number | null; signal: NodeJS.Signals | null } | null = null;
  private windows: BrowserWindow[] = [];
  private onCrashLimit: (() => void) | null = null;

  setWindows(windows: BrowserWindow[]): void {
    this.windows = windows;
  }

  setOnCrashLimit(cb: () => void): void {
    this.onCrashLimit = cb;
  }

  getStatus(): ServerStatus {
    return this.status;
  }

  getRecentLogs(): string[] {
    return [...logRing];
  }

  getPort(): number {
    return getServerPort();
  }

  private setStatus(status: ServerStatus): void {
    this.status = status;
    for (const win of this.windows) {
      if (!win.isDestroyed()) {
        win.webContents.send(IPC.SERVER_STATUS, status);
      }
    }
  }

  private routeOutput(chunk: Buffer, level: 'info' | 'warn'): void {
    const text = chunk.toString();
    for (const line of text.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      const formatted = `[backend] ${trimmed}`;
      if (level === 'info') {
        mainLog.info(formatted);
        backendFileLog.info(trimmed);
      } else {
        mainLog.warn(formatted);
        backendFileLog.warn(trimmed);
      }
      appendLogLine(trimmed);
      broadcastLog(this.windows, trimmed);
    }
  }

  async start(): Promise<void> {
    if (this.process) {
      mainLog.warn('Backend already running');
      return;
    }

    this.shuttingDown = false;
    this.backendExit = null;
    this.setStatus('starting');

    const python = runtimeVenvPython();
    const port = this.getPort();
    const backendDir = backendWorkingDir();
    const home = resolveLeagentHome();
    const frontend = frontendDir();
    const venvBin = runtimeVenvBinDir();

    const args = ['-m', 'leagent.server', '--host', '127.0.0.1', '--port', String(port)];

    const env: NodeJS.ProcessEnv = {
      ...process.env,
      VIRTUAL_ENV: runtimeVenvDir(),
      UV_PROJECT_ENVIRONMENT: runtimeVenvDir(),
      LEAGENT_HOME: home,
      LEAGENT_DESKTOP: '1',
      LEAGENT_DESKTOP_MODE: '1',
      ...(app.isPackaged ? { LEAGENT_FRONTEND_DIST: frontend } : {}),
      PYTHONDONTWRITEBYTECODE: '0',
      PYTHONUNBUFFERED: '1',
      PATH: `${venvBin}${path.delimiter}${process.env.PATH ?? ''}`,
    };

    fs.mkdirSync(path.dirname(backendLogPath()), { recursive: true });
    mainLog.info(`Starting backend: ${python} ${args.join(' ')}`);
    sendRuntimeStatus('Starting backend server…');

    this.process = spawn(python, args, {
      cwd: backendDir,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });

    this.process.stdout?.on('data', (data: Buffer) => this.routeOutput(data, 'info'));
    this.process.stderr?.on('data', (data: Buffer) => this.routeOutput(data, 'warn'));

    this.process.on('close', (code, signal) => {
      this.backendExit = { code, signal };
      mainLog.info(`Backend exited with code ${code}${signal ? ` signal ${signal}` : ''}`);
      this.process = null;

      if (!this.shuttingDown && code !== 0) {
        this.crashCount += 1;
        if (this.crashCount >= MAX_BACKEND_RESTARTS) {
          mainLog.error(`Backend crashed ${this.crashCount} times — entering maintenance`);
          this.setStatus('failed');
          sendRuntimeStatus('Backend failed repeatedly — open maintenance to repair.');
          this.onCrashLimit?.();
          return;
        }
        this.setStatus('crashed');
        mainLog.warn(`Backend crashed — restarting in 2s (attempt ${this.crashCount}/${MAX_BACKEND_RESTARTS})…`);
        sendRuntimeStatus('Backend crashed — restarting…');
        setTimeout(() => {
          if (!this.shuttingDown) void this.start();
        }, 2000);
      } else {
        this.setStatus('stopped');
      }
    });

    this.process.on('error', (err) => {
      mainLog.error('Backend spawn error:', err);
      this.process = null;
      this.setStatus('failed');
    });
  }

  async waitForHealth(): Promise<void> {
    const port = this.getPort();
    const healthUrl = `http://127.0.0.1:${port}/health`;
    sendRuntimeStatus('Waiting for backend health check…');
    let delay = 50;

    for (let i = 0; i < HEALTH_MAX_ATTEMPTS; i++) {
      if (this.backendExit) {
        const reason =
          this.backendExit.signal ? `signal ${this.backendExit.signal}` : `code ${this.backendExit.code}`;
        throw new Error(`Backend exited before becoming healthy (${reason})`);
      }

      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 2000);
        const res = await fetch(healthUrl, { signal: controller.signal });
        clearTimeout(timeout);
        if (res.ok) {
          mainLog.info('Backend health check passed');
          this.setStatus('running');
          sendRuntimeStatus('Backend ready');
          return;
        }
      } catch {
        /* not ready */
      }
      await new Promise((r) => setTimeout(r, delay));
      delay = Math.min(delay * 1.5, 1000);
    }

    throw new Error(`Backend did not become healthy after ${HEALTH_MAX_ATTEMPTS} attempts`);
  }

  async waitForFrontendReady(): Promise<void> {
    if (!app.isPackaged) return;

    const port = this.getPort();
    const frontendUrl = `http://127.0.0.1:${port}/`;
    sendRuntimeStatus('Loading frontend…');
    let delay = 100;

    for (let i = 0; i < FRONTEND_MAX_ATTEMPTS; i++) {
      if (this.backendExit) {
        const reason =
          this.backendExit.signal ? `signal ${this.backendExit.signal}` : `code ${this.backendExit.code}`;
        throw new Error(`Backend exited before frontend was ready (${reason})`);
      }

      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 2000);
        try {
          const res = await fetch(frontendUrl, { signal: controller.signal });
          const contentType = res.headers.get('content-type') ?? '';
          if (res.ok && contentType.includes('text/html')) {
            const body = await res.text();
            if (body.includes('<!doctype html') || body.includes('<div id="root"')) {
              mainLog.info('Frontend SPA is ready');
              sendRuntimeStatus('Frontend ready');
              return;
            }
          }
        } finally {
          clearTimeout(timeout);
        }
      } catch {
        /* not ready */
      }

      await new Promise((r) => setTimeout(r, delay));
      delay = Math.min(delay * 1.4, 1000);
    }

    throw new Error(`Frontend did not become ready after ${FRONTEND_MAX_ATTEMPTS} attempts`);
  }

  async restart(): Promise<void> {
    await this.stop();
    this.crashCount = 0;
    await this.start();
    await this.waitForHealth();
    if (app.isPackaged) {
      await this.waitForFrontendReady();
    }
  }

  async stop(): Promise<void> {
    this.shuttingDown = true;
    if (!this.process) return;
    mainLog.info('Stopping backend…');

    const proc = this.process;
    await new Promise<void>((resolve) => {
      const timer = setTimeout(() => {
        if (proc && !proc.killed) proc.kill('SIGKILL');
        resolve();
      }, BACKEND_KILL_TIMEOUT_MS);

      proc.once('close', () => {
        clearTimeout(timer);
        resolve();
      });

      if (process.platform === 'win32') {
        proc.kill();
      } else {
        proc.kill('SIGTERM');
      }
    });

    this.process = null;
    this.shuttingDown = false;
    this.setStatus('stopped');
  }

  isRunning(): boolean {
    return this.process !== null && !this.process.killed;
  }
}

/** Singleton used by IPC handlers and app orchestrator. */
let _server: BackendServer | null = null;

export function getBackendServer(): BackendServer {
  if (!_server) _server = new BackendServer();
  return _server;
}

/** @deprecated Use getBackendServer().getPort() */
export function getBackendPort(): number {
  return getBackendServer().getPort();
}
