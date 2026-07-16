import { Notification, app, type BrowserWindow } from 'electron';
import electronUpdater from 'electron-updater';
import { IPC, UPDATER_CHECK_INTERVAL_MS, UPDATER_INITIAL_DELAY_MS } from '../constants.js';
import { isAutoUpdateEnabled } from '../config/desktop-config.js';
import { log } from '../logger.js';
import { getMainWindow } from '../window/app-window.js';
import { safeRegisterHandle } from './safe-register.js';
import { toUpdateCheckResult } from './update-check.js';

const { autoUpdater } = electronUpdater;

let checkTimer: ReturnType<typeof setInterval> | null = null;
let updaterListenersAttached = false;

function notifyUpdateReady(): void {
  if (Notification.isSupported()) {
    new Notification({
      title: 'LeAgent Update Ready',
      body: 'A new version has been downloaded. Restart to apply.',
    }).show();
  }
}

function sendToMain(channel: string, ...args: unknown[]): void {
  const win = getMainWindow();
  if (win && !win.isDestroyed()) {
    win.webContents.send(channel, ...args);
  }
}

async function runUpdateCheck(): Promise<void> {
  if (!isAutoUpdateEnabled()) return;
  try {
    await autoUpdater.checkForUpdates();
  } catch (err) {
    log.warn('Background update check failed:', err);
  }
}

export function registerUpdaterIPC(_mainWindow: BrowserWindow): void {
  autoUpdater.logger = log;
  autoUpdater.autoDownload = isAutoUpdateEnabled();
  autoUpdater.autoInstallOnAppQuit = true;

  safeRegisterHandle(IPC.UPDATER_CHECK, async () => {
    try {
      const result = await autoUpdater.checkForUpdates();
      const remote = result?.updateInfo?.version;
      return toUpdateCheckResult(app.getVersion(), remote);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return { ok: false, updateAvailable: false, message };
    }
  });

  safeRegisterHandle(IPC.UPDATER_DOWNLOAD, async () => {
    try {
      await autoUpdater.downloadUpdate();
      return { ok: true };
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return { ok: false, message };
    }
  });

  safeRegisterHandle(IPC.UPDATER_INSTALL, () => {
    autoUpdater.quitAndInstall(false, true);
  });

  if (!updaterListenersAttached) {
    updaterListenersAttached = true;
    autoUpdater.on('update-available', (info) => {
      sendToMain(IPC.UPDATER_UPDATE_AVAILABLE, {
        version: info.version,
        releaseNotes: info.releaseNotes,
      });
    });

    autoUpdater.on('download-progress', (progress) => {
      sendToMain(IPC.UPDATER_DOWNLOAD_PROGRESS, {
        percent: progress.percent,
        bytesPerSecond: progress.bytesPerSecond,
        transferred: progress.transferred,
        total: progress.total,
      });
    });

    autoUpdater.on('update-downloaded', () => {
      sendToMain(IPC.UPDATER_DOWNLOADED);
      notifyUpdateReady();
    });
  }

  if (isAutoUpdateEnabled() && !checkTimer) {
    setTimeout(() => {
      void runUpdateCheck();
      checkTimer = setInterval(() => void runUpdateCheck(), UPDATER_CHECK_INTERVAL_MS);
    }, UPDATER_INITIAL_DELAY_MS);
  }
}

export function stopUpdaterTimer(): void {
  if (checkTimer) {
    clearInterval(checkTimer);
    checkTimer = null;
  }
}
