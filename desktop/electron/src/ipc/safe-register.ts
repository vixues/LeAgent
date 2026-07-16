import { ipcMain, type IpcMainInvokeEvent } from 'electron';

const registeredChannels = new Set<string>();

/**
 * Register an ipcMain.handle once. Subsequent calls with the same channel are no-ops.
 * Prevents "Attempted to register a second handler" on macOS activate / reopen.
 */
export function safeRegisterHandle(
  channel: string,
  listener: (event: IpcMainInvokeEvent, ...args: unknown[]) => unknown,
): void {
  if (registeredChannels.has(channel)) return;
  registeredChannels.add(channel);
  ipcMain.handle(channel, listener);
}

/** Test helper — clear the registration set between tests. */
export function resetRegisteredChannelsForTests(): void {
  registeredChannels.clear();
}

export function isChannelRegisteredForTests(channel: string): boolean {
  return registeredChannels.has(channel);
}
