type QueryKey = readonly unknown[];

interface QueryKeyRegistry {
  keys: Map<string, QueryKey>;
  register: (key: QueryKey, context?: string) => void;
  unregister: (key: QueryKey) => void;
  has: (key: QueryKey) => boolean;
  clear: () => void;
  getAll: () => Array<{ key: QueryKey; serialized: string }>;
}

const serializeKey = (key: QueryKey): string => {
  return JSON.stringify(key);
};

const createQueryKeyRegistry = (): QueryKeyRegistry => {
  const keys = new Map<string, QueryKey>();

  return {
    keys,

    register(key: QueryKey, context?: string) {
      const serialized = serializeKey(key);
      if (keys.has(serialized)) {
        if (process.env.NODE_ENV === 'development') {
          console.warn(
            `[QueryKeyRegistry] Duplicate query key detected: ${serialized}`,
            context ? `Context: ${context}` : ''
          );
        }
      }
      keys.set(serialized, key);
    },

    unregister(key: QueryKey) {
      const serialized = serializeKey(key);
      keys.delete(serialized);
    },

    has(key: QueryKey) {
      const serialized = serializeKey(key);
      return keys.has(serialized);
    },

    clear() {
      keys.clear();
    },

    getAll() {
      return Array.from(keys.entries()).map(([serialized, key]) => ({
        key,
        serialized,
      }));
    },
  };
};

const globalRegistry = createQueryKeyRegistry();

export const checkDuplicateKey = (key: QueryKey, context?: string): boolean => {
  const isDuplicate = globalRegistry.has(key);
  if (!isDuplicate) {
    globalRegistry.register(key, context);
  } else if (process.env.NODE_ENV === 'development') {
    console.warn(
      `[checkDuplicateKey] Key already exists: ${serializeKey(key)}`,
      context ? `Context: ${context}` : ''
    );
  }
  return isDuplicate;
};

export const registerQueryKey = (key: QueryKey, context?: string): void => {
  globalRegistry.register(key, context);
};

export const unregisterQueryKey = (key: QueryKey): void => {
  globalRegistry.unregister(key);
};

export const clearQueryKeyRegistry = (): void => {
  globalRegistry.clear();
};

export const getAllRegisteredKeys = (): Array<{ key: QueryKey; serialized: string }> => {
  return globalRegistry.getAll();
};

export const createUniqueQueryKey = (baseKey: QueryKey): QueryKey => {
  let counter = 0;
  let key = baseKey;
  while (globalRegistry.has(key)) {
    counter++;
    key = [...baseKey, `_${counter}`];
  }
  return key;
};

export type { QueryKey, QueryKeyRegistry };
