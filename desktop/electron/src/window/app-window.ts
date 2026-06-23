import path from 'node:path';
import { app, BrowserWindow } from 'electron';
import { IPC, TITLE_BAR_HEIGHT, type AppPage } from '../constants.js';
import { getBackendServer } from '../server/backend-server.js';
import { log } from '../logger.js';
import { setRuntimeWindows } from '../ipc/runtime.js';
import { applySavedWindowBounds, getDefaultWindowSize, persistWindowBounds } from './window-state.js';
import { closeSplash, createSplashWindow, getSplashWindow } from './splash-window.js';

let mainWindow: BrowserWindow | null = null;
let currentPage: AppPage = 'splash';

/**
 * Platform-specific frameless title-bar config so the renderer can paint its own
 * professional, system-native title bar:
 *  - macOS: keep native traffic lights (`hiddenInset`), vertically centered.
 *  - Windows: native Window Controls Overlay (min/max/close drawn by the OS).
 *  - Linux: fully frameless; the renderer draws custom window controls.
 */
function titleBarOptions(): Electron.BrowserWindowConstructorOptions {
  if (process.platform === 'darwin') {
    return {
      titleBarStyle: 'hiddenInset',
      trafficLightPosition: { x: 14, y: Math.round((TITLE_BAR_HEIGHT - 16) / 2) },
    };
  }
  if (process.platform === 'win32') {
    return {
      titleBarStyle: 'hidden',
      titleBarOverlay: {
        color: '#00000000',
        symbolColor: '#9aa0a6',
        height: TITLE_BAR_HEIGHT,
      },
    };
  }
  return { frame: false };
}

export function createMainWindow(preloadPath: string): BrowserWindow {
  const { width, height } = getDefaultWindowSize();
  mainWindow = new BrowserWindow({
    title: 'LeAgent',
    width,
    height,
    minWidth: 1024,
    minHeight: 640,
    show: false,
    backgroundColor: '#070708',
    ...titleBarOptions(),
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      spellcheck: true,
    },
  });

  applySavedWindowBounds(mainWindow);

  mainWindow.on('close', () => {
    if (mainWindow) persistWindowBounds(mainWindow);
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  const emitMaximizeState = (maximized: boolean) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send(IPC.WINDOW_MAXIMIZE_CHANGED, maximized);
    }
  };
  mainWindow.on('maximize', () => emitMaximizeState(true));
  mainWindow.on('unmaximize', () => emitMaximizeState(false));

  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    log.error(`Main window failed to load ${validatedURL} (${errorCode}): ${errorDescription}`);
  });
  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    log.error('Main window render process gone:', details);
  });

  return mainWindow;
}

export function loadPage(page: AppPage, preloadPath: string): void {
  currentPage = page;

  if (page === 'splash') {
    const splash = createSplashWindow(preloadPath);
    setRuntimeWindows(splash, mainWindow);
    return;
  }

  if (!mainWindow || mainWindow.isDestroyed()) {
    mainWindow = createMainWindow(preloadPath);
  }

  setRuntimeWindows(null, mainWindow);

  if (page === 'maintenance') {
    const maintenanceHtml = path.join(app.getAppPath(), 'maintenance', 'index.html');
    void mainWindow.loadFile(maintenanceHtml);
    return;
  }

  loadAppContent();
}

export function loadAppContent(): void {
  if (!mainWindow) return;
  currentPage = 'app';

  if (app.isPackaged) {
    const port = getBackendServer().getPort();
    void mainWindow.loadURL(`http://127.0.0.1:${port}/`);
  } else {
    void mainWindow.loadURL('http://127.0.0.1:5173');
  }
}

export function showMainWindow(): void {
  if (!mainWindow) return;
  mainWindow.show();
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.focus();
}

export function closeSplashWindow(): void {
  closeSplash();
}

export function getMainWindow(): BrowserWindow | null {
  return mainWindow;
}

export function getSplashWindowRef(): BrowserWindow | null {
  return getSplashWindow();
}

export function getCurrentPage(): AppPage {
  return currentPage;
}

export function getAllWindows(): BrowserWindow[] {
  const wins: BrowserWindow[] = [];
  const splash = getSplashWindow();
  if (splash && !splash.isDestroyed()) wins.push(splash);
  if (mainWindow && !mainWindow.isDestroyed()) wins.push(mainWindow);
  return wins;
}

/** @deprecated Use loadAppContent */
export function loadMainContent(): void {
  loadAppContent();
}
