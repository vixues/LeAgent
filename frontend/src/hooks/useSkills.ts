import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/api/client';

export interface SkillInfo {
  name: string;
  display_name: string;
  description: string;
  version: string;
  category: string;
  source: string;
  status: string;
  is_active: boolean;
  tags: string[];
}

export interface SkillResourceItem {
  path: string;
  kind: string;
  size: number;
  extension: string;
}

export interface SkillScriptItem {
  path: string;
  interpreter: string;
  size: number;
  extension: string;
}

export interface SkillDetail extends SkillInfo {
  author?: string;
  license?: string | null;
  compatibility?: string | null;
  metadata?: Record<string, unknown>;
  allowed_tools?: string[];
  resources?: SkillResourceItem[];
  scripts?: SkillScriptItem[];
  config?: Record<string, unknown>;
  error?: string;
  is_editable?: boolean;
}

export interface SkillBodyResponse {
  name: string;
  body: string;
  truncated: boolean;
}

export interface SkillFileResponse {
  name: string;
  content: string;
  truncated: boolean;
}

export interface SkillListResponse {
  skills: SkillInfo[];
  total: number;
  active_count: number;
}

export interface SkillsListParams {
  category?: string;
  tag?: string;
  search?: string;
  active_only?: boolean;
}

/** Hub search result item (matches API shape). */
export interface SkillHubItem {
  name: string;
  description: string;
  version: string;
  author?: string;
  category: string;
  downloads?: number;
  rating?: number;
  tags?: string[];
}

export interface SkillHubSearchResponse {
  skills: SkillHubItem[];
  total: number;
}

/** Optional GitHub monorepo catalog (must match backend query names). */
export interface SkillHubCatalogParams {
  gh_owner: string;
  gh_repo: string;
  gh_ref?: string;
  gh_skills_path?: string;
}

/** Skills hub (GitHub catalog) list: at most one automatic network refresh per day; persist across reloads. */
const SKILLS_HUB_CACHE_TTL_MS = 86_400_000;

type HubSearchQueryIdentity = {
  query: string;
  category: string | undefined;
  page: number;
  limit: number;
  catalog: SkillHubCatalogParams | null | undefined;
};

interface PersistedHubSearchEntry {
  v: 1;
  updatedAt: number;
  data: SkillHubSearchResponse;
}

function hubSearchStorageKey(identity: HubSearchQueryIdentity): string {
  return `leagent.skills.hubSearch.v1:${JSON.stringify(identity)}`;
}

function readPersistedHubSearch(key: string): PersistedHubSearchEntry | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as PersistedHubSearchEntry;
    if (
      parsed?.v !== 1 ||
      typeof parsed.updatedAt !== 'number' ||
      !parsed.data ||
      !Array.isArray(parsed.data.skills)
    ) {
      return null;
    }
    if (Date.now() - parsed.updatedAt > SKILLS_HUB_CACHE_TTL_MS) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function writePersistedHubSearch(key: string, data: SkillHubSearchResponse): void {
  try {
    const entry: PersistedHubSearchEntry = { v: 1, updatedAt: Date.now(), data };
    localStorage.setItem(key, JSON.stringify(entry));
  } catch {
    /* ignore quota / private mode */
  }
}

function invalidateSkillQueries(queryClient: ReturnType<typeof useQueryClient>, name?: string) {
  queryClient.invalidateQueries({ queryKey: ['skills', 'list'] });
  queryClient.invalidateQueries({ queryKey: ['skills', 'hub', 'search'] });
  queryClient.invalidateQueries({ queryKey: ['skills', 'tools', 'active'] });
  if (name) {
    queryClient.invalidateQueries({ queryKey: ['skills', 'detail', name] });
    queryClient.invalidateQueries({ queryKey: ['skills', 'body', name] });
    queryClient.invalidateQueries({ queryKey: ['skills', 'file', name] });
  }
}

export function useSkillsList(params?: SkillsListParams) {
  return useQuery({
    queryKey: ['skills', 'list', params ?? {}],
    queryFn: () =>
      apiClient.get<SkillListResponse>(
        '/skills',
        params as Record<string, string | number | boolean | undefined>
      ),
  });
}

export function useSkillDetail(name: string | undefined) {
  return useQuery({
    queryKey: ['skills', 'detail', name],
    queryFn: () => apiClient.get<SkillDetail>(`/skills/${encodeURIComponent(name!)}`),
    enabled: Boolean(name),
  });
}

export function useSkillBody(name: string | undefined) {
  return useQuery({
    queryKey: ['skills', 'body', name],
    queryFn: () => apiClient.get<SkillBodyResponse>(`/skills/${encodeURIComponent(name!)}/body`),
    enabled: Boolean(name),
  });
}

export function useSkillFile(name: string | undefined) {
  return useQuery({
    queryKey: ['skills', 'file', name],
    queryFn: () => apiClient.get<SkillFileResponse>(`/skills/${encodeURIComponent(name!)}/file`),
    enabled: Boolean(name),
  });
}

export function useUpdateSkillFile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ name, content }: { name: string; content: string }) => {
      return apiClient.put<SkillDetail>(`/skills/${encodeURIComponent(name)}/file`, { content });
    },
    onSuccess: (_data, { name }) => {
      invalidateSkillQueries(queryClient, name);
    },
  });
}

export interface SkillResourcePayload {
  path: string;
  kind: string;
  encoding: string;
  size: number;
  truncated: boolean;
  content?: string | null;
  content_base64?: string | null;
}

function encodeSkillResourceUrlPath(resourcePath: string): string {
  return resourcePath
    .replace(/^\/+/, '')
    .split('/')
    .map((seg) => encodeURIComponent(seg))
    .join('/');
}

export function useSkillResourceContent(skillName: string | undefined, resourcePath: string | undefined) {
  return useQuery({
    queryKey: ['skills', 'resource', skillName, resourcePath],
    queryFn: () =>
      apiClient.get<SkillResourcePayload>(
        `/skills/${encodeURIComponent(skillName!)}/resources/${encodeSkillResourceUrlPath(resourcePath!)}`
      ),
    enabled: Boolean(skillName && resourcePath),
  });
}

export function useActivateSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      name,
      config,
    }: {
      name: string;
      config?: Record<string, unknown>;
    }) => {
      const body = config !== undefined ? { config } : undefined;
      return apiClient.post<SkillDetail>(`/skills/${encodeURIComponent(name)}/activate`, body);
    },
    onSuccess: (_data, variables) => {
      invalidateSkillQueries(queryClient, variables.name);
    },
  });
}

export function useDeactivateSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (name: string) => {
      return apiClient.post<{ skill_name: string; is_active: boolean; message?: string }>(
        `/skills/${encodeURIComponent(name)}/deactivate`
      );
    },
    onSuccess: (_data, name) => {
      invalidateSkillQueries(queryClient, name);
    },
  });
}

export function useActiveSkillTools() {
  return useQuery({
    queryKey: ['skills', 'tools', 'active'],
    queryFn: () => apiClient.get<Record<string, unknown>[]>('/skills/tools/active'),
  });
}

export function useSkillHubSearch(
  query: string,
  category?: string,
  page = 1,
  limit = 20,
  catalog?: SkillHubCatalogParams | null
) {
  const rawParams: Record<string, string | number | undefined> = {
    query: query || '',
    category,
    page,
    limit,
  };
  if (catalog?.gh_owner && catalog?.gh_repo) {
    rawParams.gh_owner = catalog.gh_owner;
    rawParams.gh_repo = catalog.gh_repo;
    if (catalog.gh_ref) {
      rawParams.gh_ref = catalog.gh_ref;
    }
    if (catalog.gh_skills_path) {
      rawParams.gh_skills_path = catalog.gh_skills_path;
    }
  }

  const identity: HubSearchQueryIdentity = { query, category, page, limit, catalog };
  const persistKey = hubSearchStorageKey(identity);
  const persisted = readPersistedHubSearch(persistKey);

  return useQuery({
    queryKey: ['skills', 'hub', 'search', { query, category, page, limit, catalog }],
    queryFn: async () => {
      const res = await apiClient.get<SkillHubSearchResponse>('/skills/hub/search', rawParams);
      writePersistedHubSearch(persistKey, res);
      return res;
    },
    initialData: persisted?.data,
    initialDataUpdatedAt: persisted?.updatedAt,
    staleTime: SKILLS_HUB_CACHE_TTL_MS,
    gcTime: SKILLS_HUB_CACHE_TTL_MS * 2,
  });
}

export function useInstallSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      name,
      catalog,
    }: {
      name: string;
      catalog?: SkillHubCatalogParams | null;
    }) => {
      const params: Record<string, string | undefined> = {};
      if (catalog?.gh_owner && catalog?.gh_repo) {
        params.gh_owner = catalog.gh_owner;
        params.gh_repo = catalog.gh_repo;
        if (catalog.gh_ref) {
          params.gh_ref = catalog.gh_ref;
        }
        if (catalog.gh_skills_path) {
          params.gh_skills_path = catalog.gh_skills_path;
        }
      }
      return apiClient.post<{
        skill_name: string;
        version: string;
        installed: boolean;
        message?: string;
      }>(`/skills/hub/install/${encodeURIComponent(name)}`, undefined, {
        params,
      });
    },
    onSuccess: (_data, variables) => {
      invalidateSkillQueries(queryClient, variables.name);
    },
  });
}

export function useInstallSkillFromUrl() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: { url: string; sha256?: string }) => {
      return apiClient.post<SkillDetail>('/skills/install/url', {
        url: payload.url,
        sha256: payload.sha256,
      });
    },
    onSuccess: (data) => {
      invalidateSkillQueries(queryClient, data.name);
    },
  });
}
