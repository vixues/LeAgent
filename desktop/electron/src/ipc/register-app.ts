import crypto from 'node:crypto';
import fs from 'node:fs';
import { app, clipboard, ipcMain, shell } from 'electron';
import path from 'node:path';
import { IPC } from '../constants.js';
import { getInstallState } from '../config/desktop-config.js';
import { getBackendServer } from '../server/backend-server.js';
import { InstallationManager } from '../install/installation-manager.js';
import { validateInstallation } from '../install/install-validator.js';
import { userDataDir, resolveLeagentHome } from '../paths/runtime-paths.js';
import { forceOpenApp, retryBootFromMaintenance } from '../app/boot-actions.js';
import { log } from '../logger.js';

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
  ipcMain.handle(IPC.APP_GET_VERSION, () => app.getVersion());

  ipcMain.handle(IPC.APP_GET_PATHS, () => ({
    userData: app.getPath('userData'),
    logs: path.join(app.getPath('userData'), 'logs'),
    home: app.getPath('home'),
    leagentHome: resolveLeagentHome(),
  }));

  ipcMain.handle(IPC.APP_OPEN_EXTERNAL, (_event, url: string) => {
    if (typeof url === 'string' && (url.startsWith('https://') || url.startsWith('http://'))) {
      return shell.openExternal(url);
    }
  });

  ipcMain.handle(IPC.APP_OPEN_LOGS_DIR, () => {
    return shell.openPath(path.join(app.getPath('userData'), 'logs'));
  });

  ipcMain.handle(IPC.APP_SHOW_ITEM_IN_FOLDER, (_event, itemPath: string) => {
    if (typeof itemPath === 'string') {
      shell.showItemInFolder(itemPath);
    }
  });

  ipcMain.handle(IPC.APP_GET_MACHINE_FINGERPRINT, () => readOrCreateMachineFingerprint());

  ipcMain.handle(IPC.APP_GET_DIAGNOSTICS, () => collectDiagnostics());

  ipcMain.handle(IPC.APP_COPY_DIAGNOSTICS, async () => {
    try {
      const diagnostics = await collectDiagnostics();
      clipboard.writeText(JSON.stringify(diagnostics, null, 2));
      return { ok: true };
    } catch (err: unknown) {
      log.error('copyDiagnostics failed:', err);
      return { ok: false };
    }
  });

  ipcMain.handle(IPC.INSTALL_VALIDATE, () => validateInstallation());

  ipcMain.handle(IPC.INSTALL_REPAIR, async (_event, action: string) => {
    return installManager.repair(typeof action === 'string' ? action : '');
  });

  ipcMain.handle(IPC.INSTALL_REINSTALL, async () => installManager.repair('reinstall'));

  ipcMain.handle(IPC.INSTALL_RETRY_BOOT, () => retryBootFromMaintenance());

  ipcMain.handle(IPC.APP_OPEN_APP, () => {
    forceOpenApp();
  });
}
