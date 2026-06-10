import { createContext, useContext, type ReactNode } from 'react';

import type { NodeDefinition, ObjectInfo } from './objectInfo';

const RegistryContext = createContext<ObjectInfo | null>(null);

export function NodeRegistryProvider({
  value,
  children,
}: {
  value: ObjectInfo | null;
  children: ReactNode;
}) {
  return <RegistryContext.Provider value={value}>{children}</RegistryContext.Provider>;
}

/** Access the parsed `/object_info` registry from any node/component. */
export function useNodeRegistry(): ObjectInfo | null {
  return useContext(RegistryContext);
}

export function useNodeDefinition(nodeType: string): NodeDefinition | undefined {
  const registry = useContext(RegistryContext);
  return registry?.definitions[nodeType];
}
