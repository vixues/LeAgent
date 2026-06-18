import { contextBridge, ipcRenderer } from 'electron';

type Callback<T = unknown> = (data: T) => void;

const leagentBridge = {
  platform: process.platform,

  runtime: {
    onProgress: (cb: Callback<{ percent: number; detail: string }>) => {
      const handler = (_e: Electron.IpcRendererEvent, data: { percent: number; detail: string }) =>
        cb(data);
      ipcRenderer.on('runtime:progress', handler);
      return () => ipcRenderer.removeListener('runtime:progress', handler);
    },
    onStatus: (cb: Callback<string>) => {
      const handler = (_e: Electron.IpcRendererEvent, status: string) => cb(status);
      ipcRenderer.on('runtime:status', handler);
      return () => ipcRenderer.removeListener('runtime:status', handler);
    },
  },

  app: {
    getVersion: () => ipcRenderer.invoke('app:getVersion') as Promise<string>,
    getPaths: () =>
      ipcRenderer.invoke('app:getPaths') as Promise<{
        userData: string;
        logs: string;
        home: string;
      }>,
    getMachineFingerprint: () => ipcRenderer.invoke('app:getMachineFingerprint') as Promise<string>,
    openExternal: (url: string) => ipcRenderer.invoke('app:openExternal', url),
    openLogsDir: () => ipcRenderer.invoke('app:openLogsDir'),
    showItemInFolder: (p: string) => ipcRenderer.invoke('app:showItemInFolder', p),
    getDiagnostics: () => ipcRenderer.invoke('app:getDiagnostics'),
    copyDiagnostics: () => ipcRenderer.invoke('app:copyDiagnostics'),
    openApp: () => ipcRenderer.invoke('app:openApp'),
  },

  install: {
    validate: () => ipcRenderer.invoke('install:validate'),
    repair: (action: string) => ipcRenderer.invoke('install:repair', action),
    reinstall: () => ipcRenderer.invoke('install:reinstall'),
    retryBoot: () => ipcRenderer.invoke('install:retryBoot'),
    onValidation: (cb: Callback<unknown>) => {
      const handler = (_e: Electron.IpcRendererEvent, data: unknown) => cb(data);
      ipcRenderer.on('install:validation', handler);
      return () => ipcRenderer.removeListener('install:validation', handler);
    },
  },

  server: {
    restart: () => ipcRenderer.invoke('server:restart'),
    getStatus: () => ipcRenderer.invoke('server:status'),
    onLog: (cb: Callback<string>) => {
      const handler = (_e: Electron.IpcRendererEvent, line: string) => cb(line);
      ipcRenderer.on('server:log', handler);
      return () => ipcRenderer.removeListener('server:log', handler);
    },
    onStatus: (cb: Callback<string>) => {
      const handler = (_e: Electron.IpcRendererEvent, status: string) => cb(status);
      ipcRenderer.on('server:status', handler);
      return () => ipcRenderer.removeListener('server:status', handler);
    },
  },

  updater: {
    check: () => ipcRenderer.invoke('updater:check'),
    download: () => ipcRenderer.invoke('updater:download'),
    install: () => ipcRenderer.invoke('updater:install'),
    onUpdateAvailable: (cb: Callback<{ version: string; releaseNotes?: string }>) => {
      const handler = (_e: Electron.IpcRendererEvent, data: { version: string; releaseNotes?: string }) =>
        cb(data);
      ipcRenderer.on('updater:updateAvailable', handler);
      return () => ipcRenderer.removeListener('updater:updateAvailable', handler);
    },
    onDownloadProgress: (
      cb: Callback<{ percent: number; transferred: number; total: number }>,
    ) => {
      const handler = (
        _e: Electron.IpcRendererEvent,
        data: { percent: number; transferred: number; total: number },
      ) => cb(data);
      ipcRenderer.on('updater:downloadProgress', handler);
      return () => ipcRenderer.removeListener('updater:downloadProgress', handler);
    },
    onDownloaded: (cb: Callback<void>) => {
      const handler = () => cb(undefined);
      ipcRenderer.on('updater:downloaded', handler);
      return () => ipcRenderer.removeListener('updater:downloaded', handler);
    },
  },
};

contextBridge.exposeInMainWorld('leagent', leagentBridge);
