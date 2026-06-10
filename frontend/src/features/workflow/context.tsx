import { createContext, useContext, type ReactNode } from 'react';

import type { NodeDefinition, ObjectInfo } from './graph/objectInfo';

interface NodeDefsContextValue {
  objectInfo: ObjectInfo | null;
  getDefinition: (nodeType: string) => NodeDefinition | undefined;
}

const NodeDefsContext = createContext<NodeDefsContextValue>({
  objectInfo: null,
  getDefinition: () => undefined,
});

export function NodeDefsProvider({
  objectInfo,
  children,
}: {
  objectInfo: ObjectInfo | null;
  children: ReactNode;
}) {
  const value: NodeDefsContextValue = {
    objectInfo,
    getDefinition: (nodeType: string) => objectInfo?.definitions[nodeType],
  };
  return <NodeDefsContext.Provider value={value}>{children}</NodeDefsContext.Provider>;
}

export function useNodeDefs(): NodeDefsContextValue {
  return useContext(NodeDefsContext);
}
