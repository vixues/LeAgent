import { beforeEach, describe, expect, it, vi } from 'vitest';

const handlers = new Map<string, unknown>();

vi.mock('electron', () => ({
  ipcMain: {
    handle: (channel: string, listener: unknown) => {
      if (handlers.has(channel)) {
        throw new Error(`Attempted to register a second handler for '${channel}'`);
      }
      handlers.set(channel, listener);
    },
  },
}));

describe('safeRegisterHandle', () => {
  beforeEach(() => {
    handlers.clear();
  });

  it('registers a channel once and ignores subsequent calls', async () => {
    const {
      safeRegisterHandle,
      resetRegisteredChannelsForTests,
      isChannelRegisteredForTests,
    } = await import('./safe-register.js');

    resetRegisteredChannelsForTests();
    const fn = () => 'ok';
    safeRegisterHandle('test:channel', fn as never);
    expect(isChannelRegisteredForTests('test:channel')).toBe(true);
    expect(() => safeRegisterHandle('test:channel', fn as never)).not.toThrow();
    expect(handlers.size).toBe(1);
  });
});
