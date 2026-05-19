import { BrowserWindow, app } from 'electron';
import { getBackendPort } from '../backend/backend-launcher';
import { log } from '../logger';

let mainWindow: BrowserWindow | null = null;

export function createMainWindow(preloadPath: string): BrowserWindow {
  mainWindow = new BrowserWindow({
    title: 'LeAgent',
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 640,
    show: false,
    backgroundColor: '#070708',
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      spellcheck: true,
    },
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    log.error(`Main window failed to load ${validatedURL} (${errorCode}): ${errorDescription}`);
  });
  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    log.error('Main window render process gone:', details);
  });
  mainWindow.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    log.info(`[renderer:${level}] ${message} (${sourceId}:${line})`);
  });

  return mainWindow;
}

export function loadMainContent(): void {
  if (!mainWindow) return;

  if (app.isPackaged) {
    const port = getBackendPort();
    mainWindow.loadURL(`http://127.0.0.1:${port}/`);
  } else {
    const port = getBackendPort();
    mainWindow.loadURL(`http://127.0.0.1:5173`);
  }
}

export function showMainWindow(): void {
  if (!mainWindow) return;
  mainWindow.show();
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.focus();
}

export function getMainWindow(): BrowserWindow | null {
  return mainWindow;
}
