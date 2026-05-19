import type { ComponentType } from 'react';

/**
 * Wraps a dynamic import so transient network failures can retry before Suspense hangs forever.
 */
export function lazyImportWithRetry<T extends ComponentType<unknown>>(
  factory: () => Promise<{ default: T }>,
  retries = 2,
  delayMs = 400
): Promise<{ default: T }> {
  return factory().catch((err) => {
    if (retries <= 0) {
      return Promise.reject(err);
    }
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        lazyImportWithRetry(factory, retries - 1, delayMs).then(resolve, reject);
      }, delayMs);
    });
  });
}
