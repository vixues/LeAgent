import path from 'node:path';
import { app, BrowserWindow } from 'electron';
import { log } from '../logger.js';

let splashWindow: BrowserWindow | null = null;

function showSplashWindow(): void {
  if (!splashWindow || splashWindow.isDestroyed() || splashWindow.isVisible()) return;
  splashWindow.show();
  splashWindow.focus();
}

export function createSplashWindow(preloadPath: string): BrowserWindow {
  splashWindow = new BrowserWindow({
    width: 640,
    height: 400,
    frame: false,
    transparent: true,
    resizable: false,
    movable: true,
    alwaysOnTop: true,
    skipTaskbar: false,
    center: true,
    show: false,
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });

  const splashHtml = path.join(app.getAppPath(), 'splash', 'index.html');
  splashWindow.loadFile(splashHtml).catch((err: unknown) => {
    log.error('Failed to load splash window:', err);
  });

  splashWindow.once('ready-to-show', () => {
    showSplashWindow();
  });
  splashWindow.webContents.once('did-finish-load', () => {
    showSplashWindow();
  });
  splashWindow.webContents.once('did-fail-load', (_event, errorCode, errorDescription) => {
    log.error(`Splash window failed to load (${errorCode}): ${errorDescription}`);
  });
  setTimeout(showSplashWindow, 1000);

  splashWindow.on('closed', () => {
    splashWindow = null;
  });

  return splashWindow;
}

export function closeSplash(): void {
  if (!splashWindow || splashWindow.isDestroyed()) return;
  splashWindow.webContents.executeJavaScript(
    `document.querySelector('.splash-container')?.classList.add('fade-out')`,
  );
  setTimeout(() => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close();
    }
    splashWindow = null;
  }, 300);
}

export function getSplashWindow(): BrowserWindow | null {
  return splashWindow;
}
