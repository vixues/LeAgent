const STORAGE_KEY = 'leagent-machine-fingerprint-v1';
const SESSION_RESOLVED = 'leagent-machine-fingerprint-resolved';

/**
 * Resolve stable machine id from Electron (async). Cached in ``sessionStorage``
 * so subsequent :func:`getMachineFingerprint` is synchronous for API headers.
 */
export async function resolveMachineFingerprint(): Promise<string> {
  if (typeof window === 'undefined') {
    return '';
  }
  const desk = window.leagent;
  try {
    const v = await desk?.app?.getMachineFingerprint?.();
    if (v && v.length >= 8) {
      try {
        sessionStorage.setItem(SESSION_RESOLVED, v);
      } catch {
        /* ignore */
      }
      return v;
    }
  } catch {
    /* ignore */
  }
  const fp = getMachineFingerprint();
  try {
    sessionStorage.setItem(SESSION_RESOLVED, fp);
  } catch {
    /* ignore */
  }
  return fp;
}

const RESOLVE_FP_TIMEOUT_MS = 8_000;

/**
 * Never hang bootstrap: Electron ``getMachineFingerprint`` must resolve or we fall back to the
 * browser-local id from :func:`getMachineFingerprint`.
 */
export async function resolveMachineFingerprintWithTimeout(
  timeoutMs = RESOLVE_FP_TIMEOUT_MS,
): Promise<string> {
  if (typeof window === 'undefined') {
    return '';
  }
  try {
    return await Promise.race([
      resolveMachineFingerprint(),
      new Promise<string>((_, reject) => {
        window.setTimeout(() => reject(new Error('machine_fingerprint_resolve_timeout')), timeoutMs);
      }),
    ]);
  } catch {
    const fp = getMachineFingerprint();
    try {
      sessionStorage.setItem(SESSION_RESOLVED, fp);
    } catch {
      /* ignore */
    }
    return fp;
  }
}

/**
 * Stable per-browser identifier, or Electron value after :func:`resolveMachineFingerprint`.
 */
export function getMachineFingerprint(): string {
  if (typeof window !== 'undefined') {
    try {
      const fromSession = sessionStorage.getItem(SESSION_RESOLVED);
      if (fromSession && fromSession.length >= 8) {
        return fromSession;
      }
    } catch {
      /* ignore */
    }
  }
  try {
    let v = localStorage.getItem(STORAGE_KEY);
    if (!v || v.length < 8) {
      v = crypto.randomUUID();
      localStorage.setItem(STORAGE_KEY, v);
    }
    return v;
  } catch {
    return `web-${Math.random().toString(36).slice(2, 18)}`;
  }
}
