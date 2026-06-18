import { ipcMain } from 'electron';
import { IPC } from '../constants.js';
import { getBackendServer } from '../server/backend-server.js';

export function registerServerIPC(): void {
  const server = getBackendServer();

  ipcMain.handle(IPC.SERVER_RESTART, async () => {
    try {
      await server.restart();
      return { ok: true };
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return { ok: false, message };
    }
  });

  ipcMain.handle(IPC.SERVER_STATUS, () => server.getStatus());
}
