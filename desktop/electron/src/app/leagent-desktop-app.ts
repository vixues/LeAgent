import { app } from 'electron';
import { log } from '../logger.js';
import { InstallationManager } from '../install/installation-manager.js';
import { getBackendServer } from '../server/backend-server.js';
import { ensureDirs } from '../paths/runtime-paths.js';
import {
  closeSplashWindow,
  createMainWindow,
  getAllWindows,
  getMainWindow,
  loadAppContent,
  loadPage,
  showMainWindow,
} from '../window/app-window.js';
import { registerAppIPC } from '../ipc/register-app.js';
import { registerServerIPC } from '../ipc/register-server.js';
import { registerUpdaterIPC, stopUpdaterTimer } from '../ipc/register-updater.js';
import { registerWindowIPC } from '../ipc/register-window.js';
import { setRuntimeWindows } from '../ipc/runtime.js';
import { buildMenu } from '../menu.js';
import type { BrowserWindow } from 'electron';
import { setRetryBootHandler } from './boot-actions.js';
import { preloadPath as resolvePreloadPathFromDist } from '../paths/app-paths.js';
export class LeAgentDesktopApp {
  private readonly preloadPath: string;
  private readonly installManager = new InstallationManager();
  private mainWindow: BrowserWindow | null = null;
  private bootFailed = false;

  constructor(preloadPath: string) {
    this.preloadPath = preloadPath;
  }

  async start(): Promise<void> {
    ensureDirs();
    log.info('LeAgentDesktopApp — starting boot sequence');

    loadPage('splash', this.preloadPath);
    this.mainWindow = createMainWindow(this.preloadPath);
    setRuntimeWindows(null, this.mainWindow);

    registerAppIPC();
    registerServerIPC();
    registerWindowIPC();
    registerUpdaterIPC(this.mainWindow);
    buildMenu(this.mainWindow);
    setRetryBootHandler(() => this.retryBoot());

    const server = getBackendServer();
    server.setWindows(getAllWindows());
    server.setOnCrashLimit(() => {
      void this.enterMaintenance('Backend crashed too many times.');
    });

    try {
      await this.installManager.ensureInstalled();

      const validation = await this.installManager.validate();
      if (!validation.ok) {
        await this.enterMaintenance('Installation validation failed.');
        return;
      }

      await server.start();
      await server.waitForHealth();
      if (app.isPackaged) {
        await server.waitForFrontendReady();
      }

      server.setWindows(getAllWindows());
      this.showApp();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      log.error('Boot sequence failed:', err);
      this.bootFailed = true;
      await this.enterMaintenance(message);
    }
  }

  private async enterMaintenance(reason: string): Promise<void> {
    log.warn(`Entering maintenance mode: ${reason}`);
    loadPage('maintenance', this.preloadPath);
    setRuntimeWindows(null, this.mainWindow);

    if (this.mainWindow) {
      this.mainWindow.once('ready-to-show', () => {
        closeSplashWindow();
        showMainWindow();
      });
      setTimeout(() => {
        closeSplashWindow();
        showMainWindow();
      }, 500);
    }
  }

  private showApp(): void {
    if (!this.mainWindow) return;

    loadAppContent();
    serverRefreshWindows();

    this.mainWindow.once('ready-to-show', () => {
      closeSplashWindow();
      showMainWindow();
    });

    setTimeout(() => {
      if (this.mainWindow && !this.mainWindow.isVisible()) {
        closeSplashWindow();
        showMainWindow();
      }
    }, 10_000);
  }

  async retryBoot(): Promise<{ ok: boolean; message?: string }> {
    try {
      this.bootFailed = false;
      await this.installManager.ensureInstalled();
      const validation = await this.installManager.validate();
      if (!validation.ok) {
        return { ok: false, message: 'Validation still failing' };
      }

      const server = getBackendServer();
      if (!server.isRunning()) {
        await server.start();
      }
      await server.waitForHealth();
      if (app.isPackaged) {
        await server.waitForFrontendReady();
      }

      this.showApp();
      return { ok: true };
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return { ok: false, message };
    }
  }

  shutdown(): void {
    stopUpdaterTimer();
    void getBackendServer().stop();
  }

  getMainWindow(): BrowserWindow | null {
    return getMainWindow();
  }
}

function serverRefreshWindows(): void {
  getBackendServer().setWindows(getAllWindows());
}

export function resolvePreloadPath(): string {
  return resolvePreloadPathFromDist();
}
