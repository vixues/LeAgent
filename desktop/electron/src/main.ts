import path from 'node:path';
import { app, BrowserWindow } from 'electron';
import { initLogger, log } from './logger';
import { createSplashWindow, closeSplash, getSplashWindow } from './window/splash-window';
import { createMainWindow, loadMainContent, showMainWindow, getMainWindow } from './window/main-window';
import { registerAppIPC } from './ipc/app';
import { registerUpdaterIPC } from './ipc/updater';
import { setRuntimeWindows } from './ipc/runtime';
import { buildMenu } from './menu';
import { isRuntimeReady, installRuntime } from './backend/runtime-installer';
import {
  startBackend,
  waitForHealth,
  waitForFrontendReady,
  stopBackend,
} from './backend/backend-launcher';
import { ensureDirs } from './backend/runtime-paths';

// ── Single Instance Lock ──
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const win = getMainWindow();
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
}

// ── Preload path ──
const preloadPath = path.join(__dirname, 'preload.js');

// ── App lifecycle ──
app.whenReady().then(async () => {
  initLogger();
  ensureDirs();
  log.info('App ready — starting boot sequence');

  // 1. Show splash immediately
  const splash = createSplashWindow(preloadPath);

  // 2. Create main window (hidden)
  const mainWindow = createMainWindow(preloadPath);
  setRuntimeWindows(splash, mainWindow);

  // 3. Register IPC handlers
  registerAppIPC();
  registerUpdaterIPC(mainWindow);

  // 4. Build native menu
  buildMenu(mainWindow);

  // 5. Runtime install / backend start
  try {
    const ready = await isRuntimeReady();
    if (!ready) {
      if (!app.isPackaged) {
        throw new Error('Development backend venv not found. Run `cd backend && uv sync` first.');
      }
      log.info('Runtime not installed — running first-time setup');
      await installRuntime();
    } else {
      log.info('Runtime already installed');
    }

    await startBackend();
    await waitForHealth();
    if (app.isPackaged) {
      await waitForFrontendReady();
    }
  } catch (err: any) {
    log.error('Boot sequence failed:', err);
    // Show error in splash
    const sw = getSplashWindow();
    if (sw && !sw.isDestroyed()) {
      sw.webContents.executeJavaScript(
        `document.getElementById('status').textContent = 'Error: ${err.message.replace(/'/g, "\\'")}';
         document.getElementById('progressBar').style.background = '#ef4444';`,
      );
    }
    // Still try to show main window after a delay
    setTimeout(() => {
      closeSplash();
      loadMainContent();
      showMainWindow();
    }, 3000);
    return;
  }

  // 6. Load frontend and show main window
  loadMainContent();

  mainWindow.once('ready-to-show', () => {
    closeSplash();
    showMainWindow();
  });

  // Fallback: if ready-to-show doesn't fire within 10s, show anyway
  setTimeout(() => {
    if (mainWindow && !mainWindow.isVisible()) {
      closeSplash();
      showMainWindow();
    }
  }, 10000);
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    stopBackend();
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    const mainWindow = createMainWindow(preloadPath);
    loadMainContent();
    showMainWindow();
  }
});

app.on('before-quit', () => {
  stopBackend();
});
