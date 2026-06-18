import Store from 'electron-store';

export type InstallState = 'started' | 'installed' | 'needs_upgrade';

/** All keys optional — defaults are supplied via Store `defaults`. */
export interface DesktopConfigSchema {
  installState?: InstallState;
  leagentHome?: string;
  serverPort?: number;
  autoUpdate?: boolean;
  windowStyle?: 'native' | 'hidden';
  windowBounds?: {
    width: number;
    height: number;
    x?: number;
    y?: number;
    maximized?: boolean;
  };
}

const defaults = {
  serverPort: 7860,
  autoUpdate: true,
  windowStyle: 'native' as const,
};

let _store: Store<DesktopConfigSchema> | null = null;

export function getDesktopConfigStore(): Store<DesktopConfigSchema> {
  if (!_store) {
    _store = new Store<DesktopConfigSchema>({
      name: 'desktop-config',
      defaults,
    });
  }
  return _store;
}

export function getInstallState(): InstallState | undefined {
  return getDesktopConfigStore().get('installState');
}

export function setInstallState(state: InstallState): void {
  getDesktopConfigStore().set('installState', state);
}

export function getServerPort(): number {
  return getDesktopConfigStore().get('serverPort', defaults.serverPort);
}

export function getLeagentHomeOverride(): string | undefined {
  return getDesktopConfigStore().get('leagentHome');
}

export function isAutoUpdateEnabled(): boolean {
  return getDesktopConfigStore().get('autoUpdate', defaults.autoUpdate);
}

export function getWindowBounds(): DesktopConfigSchema['windowBounds'] {
  return getDesktopConfigStore().get('windowBounds');
}

export function setWindowBounds(bounds: DesktopConfigSchema['windowBounds']): void {
  getDesktopConfigStore().set('windowBounds', bounds);
}
