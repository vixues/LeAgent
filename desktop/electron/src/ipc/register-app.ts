import crypto from 'node:crypto';
import fs from 'node:fs';
import { app, clipboard, shell } from 'electron';
import path from 'node:path';
import { IPC } from '../constants.js';
import { getInstallState } from '../config/desktop-config.js';
import { getBackendServer } from '../server/backend-server.js';
import { InstallationManager } from '../install/installation-manager.js';
import { validateInstallation } from '../install/install-validator.js';
import { userDataDir, resolveLeagentHome } from '../paths/runtime-paths.js';
import { forceOpenApp, retryBootFromMaintenance } from '../app/boot-actions.js';
import { log } from '../logger.js';
import { isPathInside } from '../install/path-handlers.js';
import { safeRegisterHandle } from './safe-register.js';

const FINGERPRINT_FILE = 'machine-fingerprint';
const installManager = new InstallationManager();

function readOrCreateMachineFingerprint(): string {
  const fpPath = path.join(app.getPath('userData'), FINGERPRINT_FILE);
  try {
    const existing = fs.readFileSync(fpPath, 'utf-8').trim();
    if (existing.length >= 8) return existing;
  } catch {
    /* first run */
  }
  const fp = crypto.randomUUID();
  fs.mkdirSync(path.dirname(fpPath), { recursive: true });
  fs.writeFileSync(fpPath, fp, 'utf-8');
  return fp;
}

export async function collectDiagnostics(): Promise<Record<string, unknown>> {
  const validation = await validateInstallation();
  const server = getBackendServer();
  return {
    appVersion: app.getVersion(),
    platform: process.platform,
    arch: process.arch,
    packaged: app.isPackaged,
    installState: getInstallState(),
    paths: {
      userData: userDataDir(),
      leagentHome: resolveLeagentHome(),
      logs: path.join(userDataDir(), 'logs'),
    },
    server: {
      status: server.getStatus(),
      port: server.getPort(),
    },
    validation,
    recentBackendLogs: server.getRecentLogs().slice(-50),
  };
}

export function registerAppIPC(): void {
  safeRegisterHandle(IPC.APP_GET_VERSION, () => app.getVersion());

  safeRegisterHandle(IPC.APP_GET_PATHS, () => ({
    userData: app.getPath('userData'),
    logs: path.join(app.getPath('userData'), 'logs'),
    home: app.getPath('home'),
    leagentHome: resolveLeagentHome(),
  }));

  safeRegisterHandle(IPC.APP_OPEN_EXTERNAL, (_event, url: unknown) => {
    if (typeof url === 'string' && (url.startsWith('https://') || url.startsWith('http://'))) {
      return shell.openExternal(url);
    }
  });

  safeRegisterHandle(IPC.APP_OPEN_LOGS_DIR, () => {
    return shell.openPath(path.join(app.getPath('userData'), 'logs'));
  });

  safeRegisterHandle(IPC.APP_SHOW_ITEM_IN_FOLDER, (_event, itemPath: unknown) => {
    if (typeof itemPath !== 'string') return;
    const resolved = path.resolve(itemPath);
    const allowedRoots = [app.getPath('userData'), resolveLeagentHome()];
    if (!allowedRoots.some((root) => isPathInside(root, resolved))) return;
    shell.showItemInFolder(resolved);
  });

  safeRegisterHandle(IPC.APP_GET_MACHINE_FINGERPRINT, () => readOrCreateMachineFingerprint());

  safeRegisterHandle(IPC.APP_GET_DIAGNOSTICS, () => collectDiagnostics());

  safeRegisterHandle(IPC.APP_COPY_DIAGNOSTICS, async () => {
    try {
      const diagnostics = await collectDiagnostics();
      clipboard.writeText(JSON.stringify(diagnostics, null, 2));
      return { ok: true };
    } catch (err: unknown) {
      log.error('copyDiagnostics failed:', err);
      return { ok: false };
    }
  });

  safeRegisterHandle(IPC.INSTALL_VALIDATE, () => validateInstallation());

  safeRegisterHandle(IPC.INSTALL_REPAIR, async (_event, action: unknown) => {
    return installManager.repair(typeof action === 'string' ? action : '');
  });

  safeRegisterHandle(IPC.INSTALL_REINSTALL, async () => installManager.repair('reinstall'));

  safeRegisterHandle(IPC.INSTALL_RETRY_BOOT, () => retryBootFromMaintenance());

  safeRegisterHandle(IPC.APP_OPEN_APP, () => {
    forceOpenApp();
  });
}
