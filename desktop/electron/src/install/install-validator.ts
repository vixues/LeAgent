import fs from 'node:fs';
import net from 'node:net';
import { app } from 'electron';
import { getInstallState, getServerPort } from '../config/desktop-config.js';
import {
  getFreeDiskBytes,
  isCloudSyncedPath,
  isDirectoryWritable,
  isInsideAppInstallDir,
} from './path-handlers.js';
import {
  getPayloadHash,
  readInstalledMarker,
} from './runtime-installer.js';
import { resolveLeagentHome, runtimeVenvPython } from '../paths/runtime-paths.js';
import { MIN_DISK_SPACE_BYTES } from '../constants.js';

export type ValidationLevel = 'pass' | 'warning' | 'error';

export interface ValidationItem {
  id: string;
  label: string;
  level: ValidationLevel;
  message: string;
  repairAction?: string;
}

export interface ValidationResult {
  ok: boolean;
  items: ValidationItem[];
}

function checkPortAvailable(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.on('error', () => resolve(false));
    server.listen(port, '127.0.0.1', () => {
      server.close(() => resolve(true));
    });
  });
}

export async function validateInstallation(): Promise<ValidationResult> {
  const items: ValidationItem[] = [];
  const home = resolveLeagentHome();
  const venvPy = runtimeVenvPython();
  const port = getServerPort();

  if (!fs.existsSync(venvPy)) {
    items.push({
      id: 'venv',
      label: 'Python environment',
      level: 'error',
      message: 'Virtual environment is missing or incomplete.',
      repairAction: 'reinstall',
    });
  } else {
    items.push({
      id: 'venv',
      label: 'Python environment',
      level: 'pass',
      message: 'Virtual environment is ready.',
    });
  }

  if (app.isPackaged) {
    const marker = readInstalledMarker();
    const currentHash = getPayloadHash();
    if (!marker || marker.payloadHash !== currentHash) {
      items.push({
        id: 'payload',
        label: 'Backend dependencies',
        level: 'warning',
        message: 'Backend package lock has changed — upgrade recommended.',
        repairAction: 'upgrade',
      });
    } else {
      items.push({
        id: 'payload',
        label: 'Backend dependencies',
        level: 'pass',
        message: 'Dependencies match the bundled lockfile.',
      });
    }
  }

  if (!isDirectoryWritable(home)) {
    items.push({
      id: 'home_writable',
      label: 'Data directory',
      level: 'error',
      message: `Cannot write to LEAGENT_HOME: ${home}`,
    });
  } else if (isInsideAppInstallDir(home)) {
    items.push({
      id: 'home_location',
      label: 'Data directory',
      level: 'error',
      message: 'LEAGENT_HOME must not be inside the application install directory.',
    });
  } else if (isCloudSyncedPath(home)) {
    items.push({
      id: 'home_cloud',
      label: 'Data directory',
      level: 'warning',
      message: 'LEAGENT_HOME appears to be in a cloud-synced folder — data loss risk.',
    });
  } else {
    items.push({
      id: 'home',
      label: 'Data directory',
      level: 'pass',
      message: `Data directory is writable: ${home}`,
    });
  }

  const portFree = await checkPortAvailable(port);
  if (!portFree) {
    items.push({
      id: 'port',
      label: 'Server port',
      level: 'error',
      message: `Port ${port} is already in use.`,
    });
  } else {
    items.push({
      id: 'port',
      label: 'Server port',
      level: 'pass',
      message: `Port ${port} is available.`,
    });
  }

  const freeBytes = getFreeDiskBytes(home);
  if (freeBytes !== null && freeBytes < MIN_DISK_SPACE_BYTES) {
    items.push({
      id: 'disk',
      label: 'Disk space',
      level: 'warning',
      message: `Low disk space (${Math.round(freeBytes / (1024 * 1024))} MB free).`,
    });
  } else if (freeBytes !== null) {
    items.push({
      id: 'disk',
      label: 'Disk space',
      level: 'pass',
      message: 'Sufficient disk space available.',
    });
  }

  const state = getInstallState();
  if (state === 'started') {
    items.push({
      id: 'install_state',
      label: 'Installation',
      level: 'warning',
      message: 'Previous installation did not complete.',
      repairAction: 'reinstall',
    });
  }

  const ok = !items.some((i) => i.level === 'error');
  return { ok, items };
}
