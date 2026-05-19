let userId: string | null = null;
let workspaceId: string | null = null;
const registeredStores = new Set<string>();

export function registerNamespacedStore(name: string): void {
  registeredStores.add(name);
}

export function namespacedPersistName(name: string): string {
  const u = userId ?? 'anon';
  const w = workspaceId ?? 'none';
  return `${name}:${u}:${w}`;
}

export function setPersistIdentity(uid: string | null, wid: string | null): void {
  userId = uid;
  workspaceId = wid;
}

export function clearNamespacedStores(): void {
  const u = userId ?? 'anon';
  const w = workspaceId ?? 'none';
  for (const base of registeredStores) {
    localStorage.removeItem(`${base}:${u}:${w}`);
  }
}

/** Test-only reset of module-level identity + registry (Vitest). */
export function __resetForTests(): void {
  userId = null;
  workspaceId = null;
  registeredStores.clear();
}
