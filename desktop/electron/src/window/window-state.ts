import type { BrowserWindow } from 'electron';
import { getWindowBounds, setWindowBounds } from '../config/desktop-config.js';

const DEFAULT_WIDTH = 1440;
const DEFAULT_HEIGHT = 900;

export function applySavedWindowBounds(win: BrowserWindow): void {
  const saved = getWindowBounds();
  if (!saved) return;

  if (saved.maximized) {
    win.maximize();
    return;
  }

  win.setBounds({
    width: saved.width || DEFAULT_WIDTH,
    height: saved.height || DEFAULT_HEIGHT,
    x: saved.x,
    y: saved.y,
  });
}

export function persistWindowBounds(win: BrowserWindow): void {
  if (win.isDestroyed()) return;

  if (win.isMaximized()) {
    setWindowBounds({ width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT, maximized: true });
    return;
  }

  const bounds = win.getBounds();
  setWindowBounds({
    width: bounds.width,
    height: bounds.height,
    x: bounds.x,
    y: bounds.y,
    maximized: false,
  });
}

export function getDefaultWindowSize(): { width: number; height: number } {
  return { width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT };
}
