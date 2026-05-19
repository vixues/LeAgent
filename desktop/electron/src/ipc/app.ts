import { app, ipcMain, shell } from 'electron';
import path from 'node:path';

export function registerAppIPC(): void {
  ipcMain.handle('app:getVersion', () => {
    return app.getVersion();
  });

  ipcMain.handle('app:getPaths', () => {
    return {
      userData: app.getPath('userData'),
      logs: path.join(app.getPath('userData'), 'logs'),
      home: app.getPath('home'),
    };
  });

  ipcMain.handle('app:openExternal', (_event, url: string) => {
    if (typeof url === 'string' && (url.startsWith('https://') || url.startsWith('http://'))) {
      return shell.openExternal(url);
    }
  });

  ipcMain.handle('app:openLogsDir', () => {
    return shell.openPath(path.join(app.getPath('userData'), 'logs'));
  });

  ipcMain.handle('app:showItemInFolder', (_event, itemPath: string) => {
    if (typeof itemPath === 'string') {
      shell.showItemInFolder(itemPath);
    }
  });
}
