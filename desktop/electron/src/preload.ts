import { contextBridge, ipcRenderer } from 'electron';

type Callback<T = any> = (data: T) => void;

contextBridge.exposeInMainWorld('leagent', {
  platform: process.platform,
  version: '', // filled asynchronously below

  runtime: {
    onProgress: (cb: Callback<{ percent: number; detail: string }>) => {
      const handler = (_e: any, data: { percent: number; detail: string }) => cb(data);
      ipcRenderer.on('runtime:progress', handler);
      return () => ipcRenderer.removeListener('runtime:progress', handler);
    },
    onStatus: (cb: Callback<string>) => {
      const handler = (_e: any, status: string) => cb(status);
      ipcRenderer.on('runtime:status', handler);
      return () => ipcRenderer.removeListener('runtime:status', handler);
    },
  },

  app: {
    getVersion: () => ipcRenderer.invoke('app:getVersion'),
    getPaths: () => ipcRenderer.invoke('app:getPaths'),
    openExternal: (url: string) => ipcRenderer.invoke('app:openExternal', url),
    openLogsDir: () => ipcRenderer.invoke('app:openLogsDir'),
    showItemInFolder: (p: string) => ipcRenderer.invoke('app:showItemInFolder', p),
  },

  updater: {
    check: () => ipcRenderer.invoke('updater:check'),
    download: () => ipcRenderer.invoke('updater:download'),
    install: () => ipcRenderer.invoke('updater:install'),
    onUpdateAvailable: (cb: Callback<{ version: string; releaseNotes?: string }>) => {
      const handler = (_e: any, data: any) => cb(data);
      ipcRenderer.on('updater:updateAvailable', handler);
      return () => ipcRenderer.removeListener('updater:updateAvailable', handler);
    },
    onDownloadProgress: (cb: Callback<{ percent: number; transferred: number; total: number }>) => {
      const handler = (_e: any, data: any) => cb(data);
      ipcRenderer.on('updater:downloadProgress', handler);
      return () => ipcRenderer.removeListener('updater:downloadProgress', handler);
    },
    onDownloaded: (cb: Callback<void>) => {
      const handler = () => cb(undefined);
      ipcRenderer.on('updater:downloaded', handler);
      return () => ipcRenderer.removeListener('updater:downloaded', handler);
    },
  },
});

// Note: `version` above is set to '' at bridge creation time. The renderer
// should call `window.leagent.app.getVersion()` to fetch the actual version
// asynchronously, since contextBridge-proxied objects are immutable.
