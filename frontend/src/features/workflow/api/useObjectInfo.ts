import { useQuery } from '@tanstack/react-query';

import { apiClient } from '@/api/client';

import {
  parseObjectInfo,
  type ObjectInfo,
  type ObjectInfoResponse,
} from '../graph/objectInfo';

/**
 * Fetch and parse the backend `/object_info` node schema snapshot into the
 * editor's `NodeDefinition` registry. Cached aggressively - the node catalog
 * only changes on backend reload.
 */
export function useObjectInfo() {
  return useQuery<ObjectInfo>({
    queryKey: ['workflow', 'object-info'],
    queryFn: async () => {
      const raw = await apiClient.get<ObjectInfoResponse>('/workflow/object_info');
      return parseObjectInfo(raw);
    },
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
  });
}
