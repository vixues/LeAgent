import { IPC } from '../constants.js';
import { getBackendServer } from '../server/backend-server.js';
import { safeRegisterHandle } from './safe-register.js';

export function registerServerIPC(): void {
  const server = getBackendServer();

  safeRegisterHandle(IPC.SERVER_RESTART, async () => {
    try {
      await server.restart();
      return { ok: true };
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return { ok: false, message };
    }
  });

  safeRegisterHandle(IPC.SERVER_STATUS, () => server.getStatus());
}
