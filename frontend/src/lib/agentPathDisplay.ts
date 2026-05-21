/**
 * Human-friendly labels for agent workspace / upload paths on single-machine installs.
 */

const LOCAL_USER_UUID = '00000000-0000-0000-0000-000000000001';
const UUID_PREFIX_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_/i;
const SHORT_HEX_PREFIX_RE = /^[0-9a-f]{8}_/i;
const LEGACY_WORKSPACE_KEY_RE =
  /^00000000-0000-0000-0000-000000000001__([0-9a-f-]{36})$/i;
const COMPACT_WORKSPACE_KEY_RE = /^local__([0-9a-f]{8})$/i;

/** Strip UUID prefixes from stored upload basenames. */
export function stripStoredUploadPrefix(basename: string): string {
  if (UUID_PREFIX_RE.test(basename)) {
    return basename.replace(UUID_PREFIX_RE, '');
  }
  if (SHORT_HEX_PREFIX_RE.test(basename)) {
    return basename.replace(SHORT_HEX_PREFIX_RE, '');
  }
  return basename;
}

/** Format a code-exec workspace directory key for display. */
export function formatWorkspaceDirLabel(basename: string): string {
  const legacy = LEGACY_WORKSPACE_KEY_RE.exec(basename);
  const legacySessionId = legacy?.[1];
  if (legacySessionId) {
    return `local__${legacySessionId.replace(/-/g, '').slice(0, 8)}`;
  }
  const compact = COMPACT_WORKSPACE_KEY_RE.exec(basename);
  if (compact) {
    return basename;
  }
  if (basename.startsWith(`${LOCAL_USER_UUID}__`)) {
    const sid = basename.slice(LOCAL_USER_UUID.length + 2);
    return `local__${sid.replace(/-/g, '').slice(0, 8)}`;
  }
  return basename;
}

/** True when *path* is a session code-exec workspace root (not a user file). */
export function isCodeExecWorkspaceDir(path: string): boolean {
  const normalized = path.trim().replace(/\\/g, '/').replace(/\/+$/, '');
  if (!normalized.includes('/code-exec/')) return false;
  const base = normalized.split('/').pop() ?? '';
  if (!base || base.includes('.')) return false;
  return (
    COMPACT_WORKSPACE_KEY_RE.test(base) ||
    LEGACY_WORKSPACE_KEY_RE.test(base) ||
    base.startsWith(`${LOCAL_USER_UUID}__`)
  );
}

/** Label shown in the agent workspace file list and activity rows. */
export function formatAgentPathLabel(path: string): string {
  const normalized = path.trim().replace(/\\/g, '/');
  const base = normalized.split('/').pop() ?? normalized;
  if (!base) return path;
  if (isCodeExecWorkspaceDir(normalized)) {
    return formatWorkspaceDirLabel(base);
  }
  return stripStoredUploadPrefix(base);
}
