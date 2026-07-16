import { BrowserWindow } from 'electron';
import { IPC, TITLE_BAR_HEIGHT } from '../constants.js';
import { safeRegisterHandle } from './safe-register.js';

interface OverlayOptions {
  color?: string;
  symbolColor?: string;
}

/**
 * Window-control IPC backing the renderer's custom title bar. Each handler
 * resolves the window from the calling `webContents` so it stays correct even
 * if multiple windows ever exist.
 */
export function registerWindowIPC(): void {
  safeRegisterHandle(IPC.WINDOW_MINIMIZE, (event) => {
    BrowserWindow.fromWebContents(event.sender)?.minimize();
  });

  safeRegisterHandle(IPC.WINDOW_MAXIMIZE_TOGGLE, (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (!win) return false;
    if (win.isMaximized()) {
      win.unmaximize();
      return false;
    }
    win.maximize();
    return true;
  });

  safeRegisterHandle(IPC.WINDOW_CLOSE, (event) => {
    BrowserWindow.fromWebContents(event.sender)?.close();
  });

  safeRegisterHandle(IPC.WINDOW_IS_MAXIMIZED, (event) => {
    return BrowserWindow.fromWebContents(event.sender)?.isMaximized() ?? false;
  });

  safeRegisterHandle(IPC.WINDOW_SET_OVERLAY, (event, options: unknown) => {
    if (process.platform !== 'win32') return;
    const win = BrowserWindow.fromWebContents(event.sender);
    if (!win) return;
    const opts = (options ?? {}) as OverlayOptions;
    try {
      win.setTitleBarOverlay({
        color: opts.color ?? '#00000000',
        symbolColor: opts.symbolColor ?? '#9aa0a6',
        height: TITLE_BAR_HEIGHT,
      });
    } catch {
      /* overlay not supported on this platform/build — ignore */
    }
  });
}
