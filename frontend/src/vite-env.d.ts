/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_WS_URL: string;
  readonly VITE_API_BASE_URL?: string;
  /** Public GitHub (or doc site) URL for in-app "full documentation" link; optional. */
  readonly VITE_LEAGENT_REPO_URL?: string;
  /** Set to "true" by the desktop build to enable Electron-specific behaviour. */
  readonly VITE_DESKTOP?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** Exposed by ``desktop/electron/src/preload.ts`` when running in the Electron shell. */
interface LeAgentDesktopBridge {
  readonly platform: NodeJS.Platform;
  readonly version: string;
  checkForUpdates?: () => Promise<{ ok: boolean; version?: string; message?: string }>;
  getMachineFingerprint?: () => Promise<string>;

  runtime: {
    onProgress: (cb: (data: { percent: number; detail: string }) => void) => () => void;
    onStatus: (cb: (status: string) => void) => () => void;
  };

  app: {
    getVersion: () => Promise<string>;
    getPaths: () => Promise<{ userData: string; logs: string; home: string }>;
    openExternal: (url: string) => Promise<void>;
    openLogsDir: () => Promise<void>;
    showItemInFolder: (path: string) => void;
  };

  updater: {
    check: () => Promise<{ ok: boolean; version?: string; message?: string }>;
    download: () => Promise<{ ok: boolean; message?: string }>;
    install: () => void;
    onUpdateAvailable: (cb: (info: { version: string; releaseNotes?: string }) => void) => () => void;
    onDownloadProgress: (cb: (progress: { percent: number; transferred: number; total: number }) => void) => () => void;
    onDownloaded: (cb: () => void) => () => void;
  };
}

interface Window {
  /** Full desktop bridge (new preload contract). */
  leagent?: LeAgentDesktopBridge;
  /** @deprecated Use `window.leagent` instead. Kept for backward compat. */
  leagentDesktop?: LeAgentDesktopBridge;
}
