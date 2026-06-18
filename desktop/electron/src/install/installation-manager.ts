import { app } from 'electron';
import { log } from '../logger.js';
import { getInstallState, setInstallState } from '../config/desktop-config.js';
import {
  installRuntime,
  isRuntimeReady,
  needsRuntimeUpgrade,
  upgradeRuntimePackages,
  runAlembicUpgrade,
} from './runtime-installer.js';
import { validateInstallation, type ValidationResult } from './install-validator.js';

export class InstallationManager {
  async ensureInstalled(): Promise<void> {
    if (!app.isPackaged) {
      const ready = await isRuntimeReady();
      if (!ready) {
        throw new Error('Development backend venv not found. Run `cd backend && uv sync` first.');
      }
      return;
    }

    const state = getInstallState();

    if (state === 'needs_upgrade' || needsRuntimeUpgrade()) {
      log.info('Runtime upgrade required');
      setInstallState('needs_upgrade');
      await upgradeRuntimePackages();
      return;
    }

    const ready = await isRuntimeReady();
    if (!ready) {
      log.info('Runtime not installed — running first-time setup');
      await installRuntime(true);
      return;
    }

    log.info('Runtime already installed');
  }

  async validate(): Promise<ValidationResult> {
    return validateInstallation();
  }

  async repair(action: string): Promise<{ ok: boolean; message?: string }> {
    try {
      switch (action) {
        case 'reinstall':
          await installRuntime(true);
          return { ok: true };
        case 'upgrade':
          await upgradeRuntimePackages();
          return { ok: true };
        case 'alembic':
          await runAlembicUpgrade();
          return { ok: true };
        case 'validate':
          return { ok: (await this.validate()).ok };
        default:
          return { ok: false, message: `Unknown repair action: ${action}` };
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      log.error(`Repair action ${action} failed:`, err);
      return { ok: false, message };
    }
  }
}
