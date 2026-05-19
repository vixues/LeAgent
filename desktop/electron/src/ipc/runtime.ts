import { type BrowserWindow } from 'electron';

let _splashWindow: BrowserWindow | null = null;
let _mainWindow: BrowserWindow | null = null;

export function setRuntimeWindows(
  splash: BrowserWindow | null,
  main: BrowserWindow | null,
): void {
  _splashWindow = splash;
  _mainWindow = main;
}

export function sendRuntimeProgress(percent: number, detail: string): void {
  const payload = { percent, detail };
  _splashWindow?.webContents.send('runtime:progress', payload);
  _mainWindow?.webContents.send('runtime:progress', payload);
}

export function sendRuntimeStatus(status: string): void {
  _splashWindow?.webContents.send('runtime:status', status);
  _mainWindow?.webContents.send('runtime:status', status);
}
