import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/api/client';
import { URL_KEYS, QUERY_KEYS, CACHE_TIME } from '../../helpers/constants';

// ---- Types ----

export interface TemplateListItem {
  id: string;
  name: string;
  description: string;
  category: string;
  category_label: string;
  icon: string;
  tags: string[];
  node_count: number;
  version: string;
  source: string;
  preview_ui?: {
    nodes?: unknown[];
    edges?: unknown[];
  } | null;
}

export interface TemplateListResponse {
  templates: TemplateListItem[];
  total: number;
}

export interface TemplateCategory {
  id: string;
  label: string;
  icon: string;
  count: number;
}

export interface CategoriesResponse {
  categories: TemplateCategory[];
}

export interface TemplateDetail extends TemplateListItem {
  definition: Record<string, unknown>;
}

export interface ApplyTemplateRequest {
  name?: string;
  description?: string;
  folder_id?: string;
}

export interface ApplyTemplateResponse {
  flow_id: string;
  name: string;
  message: string;
}

// ---- Queries ----

export function useTemplates(category?: string, search?: string) {
  return useQuery<TemplateListResponse>({
    queryKey: [...QUERY_KEYS.TEMPLATES, category ?? '', search ?? ''],
    queryFn: () => {
      const params: Record<string, string> = {};
      if (category) params.category = category;
      if (search) params.search = search;
      const qs = new URLSearchParams(params).toString();
      const url = qs ? `${URL_KEYS.TEMPLATES}?${qs}` : URL_KEYS.TEMPLATES;
      return apiClient.get<TemplateListResponse>(url);
    },
    staleTime: CACHE_TIME.STALE_TIME_LONG,
    retry: 2,
  });
}

export function useTemplateCategories() {
  return useQuery<CategoriesResponse>({
    queryKey: QUERY_KEYS.TEMPLATE_CATEGORIES,
    queryFn: () => apiClient.get<CategoriesResponse>(URL_KEYS.TEMPLATE_CATEGORIES),
    staleTime: CACHE_TIME.STALE_TIME_VERY_LONG,
    retry: 2,
  });
}

export function useTemplate(templateId: string) {
  return useQuery<TemplateDetail>({
    queryKey: QUERY_KEYS.TEMPLATE(templateId),
    queryFn: () => apiClient.get<TemplateDetail>(URL_KEYS.TEMPLATE_BY_ID(templateId)),
    enabled: !!templateId,
    staleTime: CACHE_TIME.STALE_TIME_LONG,
  });
}

// ---- Mutations ----

export function useApplyTemplate() {
  const queryClient = useQueryClient();

  return useMutation<ApplyTemplateResponse, Error, { templateId: string; body: ApplyTemplateRequest }>({
    mutationFn: ({ templateId, body }) =>
      apiClient.post<ApplyTemplateResponse>(URL_KEYS.TEMPLATE_APPLY(templateId), body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.FLOWS });
    },
  });
}
