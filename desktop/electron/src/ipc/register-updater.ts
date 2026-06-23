import { Notification, type BrowserWindow } from 'electron';
import electronUpdater from 'electron-updater';
import { IPC, UPDATER_CHECK_INTERVAL_MS, UPDATER_INITIAL_DELAY_MS } from '../constants.js';
import { isAutoUpdateEnabled } from '../config/desktop-config.js';
import { log } from '../logger.js';
import { ipcMain } from 'electron';

const { autoUpdater } = electronUpdater;

let checkTimer: ReturnType<typeof setInterval> | null = null;

function notifyUpdateReady(): void {
  if (Notification.isSupported()) {
    new Notification({
      title: 'LeAgent Update Ready',
      body: 'A new version has been downloaded. Restart to apply.',
    }).show();
  }
}

async function runUpdateCheck(mainWindow: BrowserWindow): Promise<void> {
  if (!isAutoUpdateEnabled()) return;
  try {
    await autoUpdater.checkForUpdates();
  } catch (err) {
    log.warn('Background update check failed:', err);
  }
}

export function registerUpdaterIPC(mainWindow: BrowserWindow): void {
  autoUpdater.logger = log;
  autoUpdater.autoDownload = isAutoUpdateEnabled();
  autoUpdater.autoInstallOnAppQuit = true;

  ipcMain.handle(IPC.UPDATER_CHECK, async () => {
    try {
      const result = await autoUpdater.checkForUpdates();
      return { ok: true, version: result?.updateInfo?.version };
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return { ok: false, message };
    }
  });

  ipcMain.handle(IPC.UPDATER_DOWNLOAD, async () => {
    try {
      await autoUpdater.downloadUpdate();
      return { ok: true };
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return { ok: false, message };
    }
  });

  ipcMain.handle(IPC.UPDATER_INSTALL, () => {
    autoUpdater.quitAndInstall(false, true);
  });

  autoUpdater.on('update-available', (info) => {
    mainWindow.webContents.send(IPC.UPDATER_UPDATE_AVAILABLE, {
      version: info.version,
      releaseNotes: info.releaseNotes,
    });
  });

  autoUpdater.on('download-progress', (progress) => {
    mainWindow.webContents.send(IPC.UPDATER_DOWNLOAD_PROGRESS, {
      percent: progress.percent,
      bytesPerSecond: progress.bytesPerSecond,
      transferred: progress.transferred,
      total: progress.total,
    });
  });

  autoUpdater.on('update-downloaded', () => {
    mainWindow.webContents.send(IPC.UPDATER_DOWNLOADED);
    notifyUpdateReady();
  });

  if (isAutoUpdateEnabled()) {
    setTimeout(() => {
      void runUpdateCheck(mainWindow);
      checkTimer = setInterval(() => void runUpdateCheck(mainWindow), UPDATER_CHECK_INTERVAL_MS);
    }, UPDATER_INITIAL_DELAY_MS);
  }
}

export function stopUpdaterTimer(): void {
  if (checkTimer) {
    clearInterval(checkTimer);
    checkTimer = null;
  }
}
