/**
 * Pure helpers for desktop updater check results (testable without electron-updater).
 */

export interface UpdateCheckResult {
  ok: boolean;
  updateAvailable: boolean;
  version?: string;
  message?: string;
}

/** Compare dotted numeric versions; returns true when remote is strictly newer than current. */
export function isRemoteNewer(current: string, remote: string): boolean {
  const parse = (v: string): number[] =>
    v
      .replace(/^v/i, '')
      .split(/[.+-]/)
      .map((p) => Number.parseInt(p, 10))
      .map((n) => (Number.isFinite(n) ? n : 0));

  const a = parse(current);
  const b = parse(remote);
  const len = Math.max(a.length, b.length);
  for (let i = 0; i < len; i++) {
    const left = a[i] ?? 0;
    const right = b[i] ?? 0;
    if (right > left) return true;
    if (right < left) return false;
  }
  return false;
}

export function toUpdateCheckResult(
  currentVersion: string,
  remoteVersion: string | undefined | null,
): UpdateCheckResult {
  if (!remoteVersion) {
    return { ok: true, updateAvailable: false };
  }
  const updateAvailable = isRemoteNewer(currentVersion, remoteVersion);
  return {
    ok: true,
    updateAvailable,
    version: remoteVersion,
  };
}
