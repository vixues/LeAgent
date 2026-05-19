import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/api/client';

// Types
export interface MCPServerInfo {
  name: string;
  transport: string;
  enabled: boolean;
  auto_connect: boolean;
  connected: boolean;
  tool_count: number;
  prompt_count: number;
  resource_count: number;
}

export interface MCPServerDetail extends MCPServerInfo {
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
  description?: string;
  health?: Record<string, unknown>;
  tools?: Array<{ name: string; description?: string }>;
  prompts?: Array<{ name: string; description?: string }>;
  resources?: Array<{ name: string; description?: string }>;
}

export interface MCPHealthResponse {
  servers: Record<string, Record<string, unknown>>;
  connected_count: number;
  total_count: number;
}

export interface MCPToolCallResponse {
  server_name: string;
  tool_name: string;
  success: boolean;
  result?: unknown;
  error?: string;
  latency_ms: number;
}

export interface MCPServerCreateInput {
  name: string;
  transport: 'stdio' | 'sse';
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
  enabled?: boolean;
  auto_connect?: boolean;
  description?: string;
}

export interface MCPToolDict {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  server_name: string;
}

export function useMCPServers() {
  return useQuery({
    queryKey: ['mcp', 'servers'],
    queryFn: async () => {
      return apiClient.get<MCPServerInfo[]>('/mcp/servers');
    },
  });
}

export function useMCPServerDetail(name: string) {
  return useQuery({
    queryKey: ['mcp', 'servers', name],
    queryFn: async () => {
      return apiClient.get<MCPServerDetail>(`/mcp/servers/${encodeURIComponent(name)}`);
    },
    enabled: !!name,
  });
}

export function useMCPTools(serverName?: string) {
  return useQuery({
    queryKey: ['mcp', 'tools', serverName ?? 'all'],
    queryFn: async () => {
      return apiClient.get<MCPToolDict[]>('/mcp/tools', {
        server_name: serverName,
      });
    },
  });
}

export function useMCPHealth() {
  return useQuery({
    queryKey: ['mcp', 'health'],
    queryFn: async () => {
      return apiClient.get<MCPHealthResponse>('/mcp/health');
    },
  });
}

function invalidateMCPLists(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ['mcp', 'servers'] });
  queryClient.invalidateQueries({ queryKey: ['mcp', 'tools'] });
  queryClient.invalidateQueries({ queryKey: ['mcp', 'health'] });
}

export function useAddMCPServer() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: MCPServerCreateInput) => {
      return apiClient.post<MCPServerInfo>('/mcp/servers', data);
    },
    onSuccess: () => {
      invalidateMCPLists(queryClient);
    },
  });
}

export function useRemoveMCPServer() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (name: string) => {
      return apiClient.delete(`/mcp/servers/${encodeURIComponent(name)}`);
    },
    onSuccess: (_, name) => {
      invalidateMCPLists(queryClient);
      queryClient.removeQueries({ queryKey: ['mcp', 'servers', name] });
    },
  });
}

export function useConnectMCPServer() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (name: string) => {
      return apiClient.post<{
        server_name: string;
        connected: boolean;
        message: string;
      }>(`/mcp/servers/${encodeURIComponent(name)}/connect`);
    },
    onSuccess: (_, name) => {
      invalidateMCPLists(queryClient);
      queryClient.invalidateQueries({ queryKey: ['mcp', 'servers', name] });
    },
  });
}

export function useDisconnectMCPServer() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (name: string) => {
      return apiClient.post<{
        server_name: string;
        connected: boolean;
        message: string;
      }>(`/mcp/servers/${encodeURIComponent(name)}/disconnect`);
    },
    onSuccess: (_, name) => {
      invalidateMCPLists(queryClient);
      queryClient.invalidateQueries({ queryKey: ['mcp', 'servers', name] });
    },
  });
}

export function useCallMCPTool() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      serverName,
      toolName,
      arguments: args = {},
    }: {
      serverName: string;
      toolName: string;
      arguments?: Record<string, unknown>;
    }) => {
      return apiClient.post<MCPToolCallResponse>(
        '/mcp/tools/call',
        { tool_name: toolName, arguments: args },
        { params: { server_name: serverName } }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcp', 'health'] });
    },
  });
}
