import { ipcMain, type BrowserWindow } from 'electron';
import { autoUpdater } from 'electron-updater';
import { log } from '../logger';

export function registerUpdaterIPC(mainWindow: BrowserWindow): void {
  autoUpdater.logger = log;
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;

  ipcMain.handle('updater:check', async () => {
    try {
      const result = await autoUpdater.checkForUpdates();
      return { ok: true, version: result?.updateInfo?.version };
    } catch (err: any) {
      return { ok: false, message: err.message };
    }
  });

  ipcMain.handle('updater:download', async () => {
    try {
      await autoUpdater.downloadUpdate();
      return { ok: true };
    } catch (err: any) {
      return { ok: false, message: err.message };
    }
  });

  ipcMain.handle('updater:install', () => {
    autoUpdater.quitAndInstall(false, true);
  });

  autoUpdater.on('update-available', (info) => {
    mainWindow.webContents.send('updater:updateAvailable', {
      version: info.version,
      releaseNotes: info.releaseNotes,
    });
  });

  autoUpdater.on('download-progress', (progress) => {
    mainWindow.webContents.send('updater:downloadProgress', {
      percent: progress.percent,
      bytesPerSecond: progress.bytesPerSecond,
      transferred: progress.transferred,
      total: progress.total,
    });
  });

  autoUpdater.on('update-downloaded', () => {
    mainWindow.webContents.send('updater:downloaded');
  });
}
