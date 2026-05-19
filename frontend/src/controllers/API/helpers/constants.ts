export const URL_KEYS = {
  // Auth
  AUTH_LOGIN: '/auth/login',
  AUTH_LOGOUT: '/auth/logout',
  AUTH_REGISTER: '/auth/register',
  AUTH_REFRESH: '/auth/refresh',
  AUTH_PROFILE: '/auth/me',
  AUTH_CHANGE_PASSWORD: '/auth/change-password',

  // Flows (served by the workflow engine router)
  FLOWS: '/workflow/flows',
  FLOWS_RECENT: '/workflow/flows/recent',
  FLOW_BY_ID: (id: string) => `/workflow/flows/${id}`,
  FLOW_DUPLICATE: (id: string) => `/workflow/flows/${id}/duplicate`,
  FLOW_EXPORT: (id: string) => `/workflow/flows/${id}/export`,
  FLOW_IMPORT: '/workflow/flows/import',
  FLOW_VALIDATE: (id: string) => `/workflow/flows/${id}/validate`,

  // Flow Execution
  FLOW_BUILD: (id: string) => `/workflow/flows/${id}/build`,
  FLOW_RUN: (id: string) => `/workflow/flows/${id}/run`,

  // Prompt queue (new canonical run surface)
  WORKFLOW_PROMPTS: '/workflow/prompts',
  WORKFLOW_PROMPT_BY_ID: (id: string) => `/workflow/prompts/${id}`,
  WORKFLOW_PROMPT_CANCEL: (id: string) => `/workflow/prompts/${id}/cancel`,
  WORKFLOW_PROMPT_PAUSE: (id: string) => `/workflow/prompts/${id}/pause`,
  WORKFLOW_PROMPT_RESUME: (id: string) => `/workflow/prompts/${id}/resume`,

  // Engine introspection/admin
  WORKFLOW_OBJECT_INFO: '/workflow/object_info',
  WORKFLOW_RELOAD_NODES: '/workflow/admin/reload-nodes',
  WORKFLOW_REPLACEMENTS: '/workflow/admin/replacements',

  // Messages
  MESSAGES: '/messages',
  MESSAGE_BY_ID: (id: string) => `/messages/${id}`,
  MESSAGES_BY_SESSION: (sessionId: string) => `/sessions/${sessionId}/messages`,
  MESSAGE_STREAM: '/messages/stream',

  // Sessions
  SESSIONS: '/sessions',
  SESSION_BY_ID: (id: string) => `/sessions/${id}`,

  // Tasks
  TASKS: '/tasks',
  TASK_BY_ID: (id: string) => `/tasks/${id}`,
  TASK_STATUS: (id: string) => `/tasks/${id}/status`,
  TASK_CANCEL: (id: string) => `/tasks/${id}/cancel`,
  TASK_RETRY: (id: string) => `/tasks/${id}/retry`,
  TASK_LOGS: (id: string) => `/tasks/${id}/logs`,

  // Tools
  TOOLS: '/tools',
  TOOL_BY_ID: (id: string) => `/tools/${id}`,
  TOOL_SCHEMA: (id: string) => `/tools/${id}/schema`,
  TOOL_EXECUTE: (id: string) => `/tools/${id}/execute`,
  TOOL_CATEGORIES: '/tools/categories',

  // Model Providers
  MODELS_PROVIDERS: '/models/providers',
  MODELS_PROVIDER_BY_ID: (id: string) => `/models/providers/${id}`,
  MODELS_PROVIDER_HEALTH: (id: string) => `/models/providers/${id}/health`,
  MODELS_TEST: '/models/test',
  MODELS_LIST: (providerId: string) => `/models/providers/${providerId}/models`,

  // Files
  FILES: '/files',
  FILE_BY_ID: (id: string) => `/files/${id}`,
  FILE_UPLOAD: '/files/upload',
  FILE_DOWNLOAD: (id: string) => `/files/${id}/download`,
  FILE_PREVIEW: (id: string) => `/files/${id}/preview`,

  // Documents (knowledge base)
  KNOWLEDGE: '/documents',
  KNOWLEDGE_BY_ID: (id: string) => `/documents/${id}`,
  KNOWLEDGE_SEARCH: '/documents/search',
  KNOWLEDGE_INGEST: '/documents/upload',

  // Rules
  RULES: '/rules',
  RULE_BY_ID: (id: string) => `/rules/${id}`,
  RULE_TEST: (id: string) => `/rules/${id}/test`,

  // Webhooks
  WEBHOOKS: '/webhooks',
  WEBHOOK_BY_ID: (id: string) => `/webhooks/${id}`,

  // System
  SYSTEM_HEALTH: '/health',
  SYSTEM_VERSION: '/version',
  SYSTEM_SETTINGS: '/settings',

  // Cron
  CRON_JOBS: '/cron',
  CRON_JOB_BY_ID: (id: string) => `/cron/${id}`,
  CRON_JOB_HISTORY: (id: string) => `/cron/${id}/history`,
  CRON_JOB_STATS: (id: string) => `/cron/${id}/stats`,
  CRON_JOB_NEXT_RUNS: (id: string) => `/cron/${id}/next-runs`,
  CRON_JOB_RUN: (id: string) => `/cron/${id}/run`,
  CRON_JOB_PAUSE: (id: string) => `/cron/${id}/pause`,
  CRON_JOB_RESUME: (id: string) => `/cron/${id}/resume`,
  CRON_JOB_CLONE: (id: string) => `/cron/${id}/clone`,
  CRON_HEALTH: '/cron/health',
  CRON_STATS: '/cron/stats',
  CRON_PREVIEW_NEXT_RUNS: '/cron/preview-next-runs',

  // Workflow Executions
  FLOW_EXECUTIONS: (flowId: string) => `/workflow/flows/${flowId}/executions`,
  FLOW_EXECUTION_BY_ID: (execId: string) => `/workflow/executions/${execId}`,
  FLOW_EXECUTION_CANCEL: (execId: string) => `/workflow/executions/${execId}/cancel`,
  FLOW_EXECUTION_PAUSE: (execId: string) => `/workflow/executions/${execId}/pause`,
  FLOW_EXECUTION_RESUME: (execId: string) => `/workflow/executions/${execId}/resume`,

  // Templates
  TEMPLATES: '/templates',
  TEMPLATE_BY_ID: (id: string) => `/templates/${id}`,
  TEMPLATE_CATEGORIES: '/templates/categories',
  TEMPLATE_APPLY: (id: string) => `/templates/${id}/apply`,

  // Admin
  ADMIN_USERS: '/admin/users',
  ADMIN_USER_BY_ID: (id: string) => `/admin/users/${id}`,
  ADMIN_API_KEYS: '/admin/api-keys',
  ADMIN_STATS: '/admin/stats',
  ADMIN_LOGS: '/admin/logs',
} as const;

export const QUERY_KEYS = {
  FLOWS: ['flows'] as const,
  FLOW: (id: string) => ['flows', id] as const,
  FLOW_VALIDATION: (id: string) => ['flows', id, 'validation'] as const,

  MESSAGES: ['messages'] as const,
  MESSAGE: (id: string) => ['messages', id] as const,
  SESSION_MESSAGES: (sessionId: string) => ['sessions', sessionId, 'messages'] as const,

  SESSIONS: ['sessions'] as const,
  SESSION: (id: string) => ['sessions', id] as const,

  TASKS: ['tasks'] as const,
  TASK: (id: string) => ['tasks', id] as const,
  TASK_STATUS: (id: string) => ['tasks', id, 'status'] as const,

  TOOLS: ['tools'] as const,
  TOOL: (id: string) => ['tools', id] as const,
  TOOL_SCHEMA: (id: string) => ['tools', id, 'schema'] as const,
  TOOL_CATEGORIES: ['tools', 'categories'] as const,

  PROVIDERS: ['providers'] as const,
  PROVIDER: (id: string) => ['providers', id] as const,
  PROVIDER_HEALTH: (id: string) => ['providers', id, 'health'] as const,
  PROVIDER_MODELS: (id: string) => ['providers', id, 'models'] as const,

  FILES: ['files'] as const,
  FILE: (id: string) => ['files', id] as const,

  KNOWLEDGE: ['documents'] as const,
  KNOWLEDGE_ITEM: (id: string) => ['documents', id] as const,
  KNOWLEDGE_SEARCH: (query: string) => ['documents', 'search', query] as const,

  RULES: ['rules'] as const,
  RULE: (id: string) => ['rules', id] as const,

  CRON_JOBS: ['cron'] as const,
  CRON_JOB: (id: string) => ['cron', id] as const,
  CRON_JOB_HISTORY: (id: string) => ['cron', id, 'history'] as const,
  CRON_JOB_STATS: (id: string) => ['cron', id, 'stats'] as const,
  CRON_JOB_NEXT_RUNS: (id: string) => ['cron', id, 'next-runs'] as const,
  CRON_HEALTH: ['cron', 'health'] as const,
  CRON_STATS: ['cron', 'stats'] as const,

  EXECUTIONS: (flowId: string) => ['flows', flowId, 'executions'] as const,
  EXECUTION: (execId: string) => ['executions', execId] as const,

  TEMPLATES: ['templates'] as const,
  TEMPLATE: (id: string) => ['templates', id] as const,
  TEMPLATE_CATEGORIES: ['templates', 'categories'] as const,

  AUTH_USER: ['auth', 'user'] as const,
  AUTH_PROFILE: ['auth', 'profile'] as const,

  ADMIN_USERS: ['admin', 'users'] as const,
  ADMIN_USER: (id: string) => ['admin', 'users', id] as const,
  ADMIN_STATS: ['admin', 'stats'] as const,
  ADMIN_LOGS: ['admin', 'logs'] as const,

  SYSTEM_HEALTH: ['system', 'health'] as const,
  SYSTEM_SETTINGS: ['system', 'settings'] as const,
} as const;

export const CACHE_TIME = {
  STALE_TIME_SHORT: 30 * 1000,
  STALE_TIME_MEDIUM: 2 * 60 * 1000,
  STALE_TIME_LONG: 5 * 60 * 1000,
  STALE_TIME_VERY_LONG: 30 * 60 * 1000,
  GC_TIME: 10 * 60 * 1000,
} as const;

export const PAGINATION = {
  DEFAULT_PAGE_SIZE: 20,
  MAX_PAGE_SIZE: 100,
} as const;
