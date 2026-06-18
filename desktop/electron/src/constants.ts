/** Default local backend port. */
export const DEFAULT_SERVER_PORT = 7860;

/** Max automatic backend restarts after crash before entering maintenance. */
export const MAX_BACKEND_RESTARTS = 3;

/** Health-check polling (exponential backoff capped at 1s). */
export const HEALTH_MAX_ATTEMPTS = 240;

/** Frontend SPA readiness polling after /health passes. */
export const FRONTEND_MAX_ATTEMPTS = 120;

/** Graceful backend shutdown before SIGKILL (ms). */
export const BACKEND_KILL_TIMEOUT_MS = 10_000;

/** Auto-update check interval (ms). */
export const UPDATER_CHECK_INTERVAL_MS = 60 * 60 * 1000;

/** Delay before first auto-update check after launch (ms). */
export const UPDATER_INITIAL_DELAY_MS = 30_000;

/** Minimum free disk space warning threshold (bytes). */
export const MIN_DISK_SPACE_BYTES = 2 * 1024 * 1024 * 1024;

export const IPC = {
  APP_GET_VERSION: 'app:getVersion',
  APP_GET_PATHS: 'app:getPaths',
  APP_OPEN_EXTERNAL: 'app:openExternal',
  APP_OPEN_LOGS_DIR: 'app:openLogsDir',
  APP_SHOW_ITEM_IN_FOLDER: 'app:showItemInFolder',
  APP_GET_MACHINE_FINGERPRINT: 'app:getMachineFingerprint',
  APP_GET_DIAGNOSTICS: 'app:getDiagnostics',
  APP_COPY_DIAGNOSTICS: 'app:copyDiagnostics',

  RUNTIME_PROGRESS: 'runtime:progress',
  RUNTIME_STATUS: 'runtime:status',

  SERVER_RESTART: 'server:restart',
  SERVER_STATUS: 'server:status',
  SERVER_LOG: 'server:log',

  INSTALL_VALIDATE: 'install:validate',
  INSTALL_REPAIR: 'install:repair',
  INSTALL_REINSTALL: 'install:reinstall',
  INSTALL_RETRY_BOOT: 'install:retryBoot',
  INSTALL_VALIDATION: 'install:validation',

  APP_OPEN_APP: 'app:openApp',

  UPDATER_CHECK: 'updater:check',
  UPDATER_DOWNLOAD: 'updater:download',
  UPDATER_INSTALL: 'updater:install',
  UPDATER_UPDATE_AVAILABLE: 'updater:updateAvailable',
  UPDATER_DOWNLOAD_PROGRESS: 'updater:downloadProgress',
  UPDATER_DOWNLOADED: 'updater:downloaded',
} as const;

export type AppPage = 'splash' | 'maintenance' | 'app';
