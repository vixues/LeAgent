import { loadAppContent, showMainWindow } from '../window/app-window.js';

type RetryBootFn = () => Promise<{ ok: boolean; message?: string }>;

let retryBootFn: RetryBootFn | null = null;

export function setRetryBootHandler(fn: RetryBootFn): void {
  retryBootFn = fn;
}

export async function retryBootFromMaintenance(): Promise<{ ok: boolean; message?: string }> {
  if (!retryBootFn) {
    return { ok: false, message: 'Application is not ready for retry.' };
  }
  return retryBootFn();
}

export function forceOpenApp(): void {
  loadAppContent();
  showMainWindow();
}
