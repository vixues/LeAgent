/// <reference types="vite/client" />
/// <reference types="react" />
/// <reference types="react-dom" />

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

/** How window controls are rendered in the desktop shell. */
type LeAgentTitleBarStyle = 'mac' | 'overlay' | 'custom';

/** Exposed by ``desktop/electron/src/preload.ts`` when running in the Electron shell. */
interface LeAgentDesktopBridge {
  readonly platform: NodeJS.Platform;

  window: {
    readonly style: LeAgentTitleBarStyle;
    minimize: () => Promise<void>;
    maximizeToggle: () => Promise<boolean>;
    close: () => Promise<void>;
    isMaximized: () => Promise<boolean>;
    setOverlay: (options: { color?: string; symbolColor?: string }) => Promise<void>;
    onMaximizeChanged: (cb: (maximized: boolean) => void) => () => void;
  };

  runtime: {
    onProgress: (cb: (data: { percent: number; detail: string }) => void) => () => void;
    onStatus: (cb: (status: string) => void) => () => void;
  };

  app: {
    getVersion: () => Promise<string>;
    getPaths: () => Promise<{ userData: string; logs: string; home: string; leagentHome: string }>;
    getMachineFingerprint: () => Promise<string>;
    openExternal: (url: string) => Promise<void>;
    openLogsDir: () => Promise<void>;
    showItemInFolder: (path: string) => void;
    getDiagnostics: () => Promise<Record<string, unknown>>;
    copyDiagnostics: () => Promise<{ ok: boolean }>;
    openApp: () => Promise<void>;
  };

  install: {
    validate: () => Promise<unknown>;
    repair: (action: string) => Promise<{ ok: boolean; message?: string }>;
    reinstall: () => Promise<{ ok: boolean; message?: string }>;
    retryBoot: () => Promise<{ ok: boolean; message?: string }>;
    onValidation: (cb: (data: unknown) => void) => () => void;
  };

  server: {
    restart: () => Promise<{ ok: boolean }>;
    getStatus: () => Promise<string>;
    onLog: (cb: (line: string) => void) => () => void;
    onStatus: (cb: (status: string) => void) => () => void;
  };

  updater: {
    check: () => Promise<{ ok: boolean; updateAvailable?: boolean; version?: string; message?: string }>;
    download: () => Promise<{ ok: boolean; message?: string }>;
    install: () => void;
    onUpdateAvailable: (cb: (info: { version: string; releaseNotes?: string }) => void) => () => void;
    onDownloadProgress: (cb: (progress: { percent: number; transferred: number; total: number }) => void) => () => void;
    onDownloaded: (cb: () => void) => () => void;
  };
}

interface Window {
  leagent?: LeAgentDesktopBridge;
}
