import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/api/client';
import type { RuleSetInfo, RuleSetDetail, RuleSetCreateData, RuleSetUpdateData, RuleEvaluateResponse } from '@/types/admin';

export function useRulesList(enabled?: boolean) {
  return useQuery({
    queryKey: ['rules', 'list', enabled],
    queryFn: async () => {
      const params: Record<string, string | number | boolean | undefined> = {};
      if (enabled !== undefined) params.enabled = enabled;
      return apiClient.get<RuleSetInfo[]>('/rules', params);
    },
  });
}

export function useRuleSetDetail(ruleSetId: string | null) {
  return useQuery({
    queryKey: ['rules', 'detail', ruleSetId],
    queryFn: () => apiClient.get<RuleSetDetail>(`/rules/${ruleSetId}`),
    enabled: !!ruleSetId,
  });
}

export function useCreateRuleSet() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: RuleSetCreateData) => {
      return apiClient.post<RuleSetInfo>('/rules', data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules', 'list'] });
    },
  });
}

export function useUpdateRuleSet() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: RuleSetUpdateData }) => {
      return apiClient.put<RuleSetDetail>(`/rules/${id}`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] });
    },
  });
}

export function useEvaluateRuleSet() {
  return useMutation({
    mutationFn: async ({
      id,
      data,
      tags,
      skip_disabled,
      fail_fast,
    }: {
      id: string;
      data: Record<string, unknown>;
      tags?: string[];
      skip_disabled?: boolean;
      fail_fast?: boolean;
    }) => {
      return apiClient.post<RuleEvaluateResponse>(`/rules/${id}/evaluate`, {
        data,
        tags,
        skip_disabled,
        fail_fast,
      });
    },
  });
}

export function useReloadRules() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      return apiClient.post<{ message: string }>('/rules/reload');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] });
    },
  });
}
