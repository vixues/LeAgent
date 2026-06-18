import log from 'electron-log/main.js';
import path from 'node:path';
import { app } from 'electron';

export function initLogger(): void {
  const logsDir = path.join(app.getPath('userData'), 'logs');

  log.transports.file.resolvePathFn = () => path.join(logsDir, 'main.log');
  log.transports.file.maxSize = 10 * 1024 * 1024; // 10 MB
  log.transports.file.format = '{y}-{m}-{d} {h}:{i}:{s}.{ms} [{level}] {text}';
  log.transports.console.format = '{h}:{i}:{s}.{ms} [{level}] {text}';

  log.initialize();
  log.info(`LeAgent Desktop v${app.getVersion()} — logs: ${logsDir}`);
}

/** Named file logger (e.g. `backend` → `logs/backend.log`). */
export function createFileLogger(logId: string, logFileName: string): typeof log {
  const logsDir = path.join(app.getPath('userData'), 'logs');
  const child = log.create({ logId });
  child.transports.file.resolvePathFn = () => path.join(logsDir, logFileName);
  child.transports.file.maxSize = 10 * 1024 * 1024;
  child.transports.file.format = '{y}-{m}-{d} {h}:{i}:{s}.{ms} [{level}] {text}';
  return child;
}

export { log };
