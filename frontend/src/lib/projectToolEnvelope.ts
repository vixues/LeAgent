/**
 * Shared parsing for ``coding_agent`` / ``project_*`` tool result envelopes
 * and argument helpers — used by {@link ProjectToolCallBlock} and the chat
 * workspace agent code tab.
 */
import type { Message, ToolCall } from '@/types/chat';
import { resolveCodingProjectPreviewHref } from '@/lib/previewUrl';

export interface ActivityRow {
  tool?: string;
  path?: string;
  summary?: string;
}

export function strArg(args: Record<string, unknown>, key: string): string {
  const v = args[key];
  return typeof v === 'string' ? v : '';
}

/** UUID from ``coding_project_run`` / related tool result bodies. */
export function extractCodingProjectId(result: unknown): string | null {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return null;
  const pid = (result as Record<string, unknown>).project_id;
  return typeof pid === 'string' && pid.trim().length > 0 ? pid.trim() : null;
}

export function fmtJson(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2);
}

export function parseActivity(result: unknown): ActivityRow[] {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return [];
  const act = (result as Record<string, unknown>).activity;
  if (!Array.isArray(act)) return [];
  const out: ActivityRow[] = [];
  for (const row of act) {
    if (!row || typeof row !== 'object') continue;
    const r = row as Record<string, unknown>;
    out.push({
      tool: typeof r.tool === 'string' ? r.tool : undefined,
      path: typeof r.path === 'string' ? r.path : undefined,
      summary: typeof r.summary === 'string' ? r.summary : undefined,
    });
  }
  return out;
}

export function changedFilesList(result: unknown): string[] {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return [];
  const cf = (result as Record<string, unknown>).changed_files;
  if (!Array.isArray(cf)) return [];
  return cf.filter((x): x is string => typeof x === 'string' && x.trim().length > 0);
}

/** Normalize filesystem paths for equality checks (chat args vs envelope paths). */
export function normalizeProjectPath(p: string): string {
  return p.trim().replace(/\\/g, '/').replace(/\/+$/, '');
}

export function pathsMatch(a: string, b: string): boolean {
  return normalizeProjectPath(a) === normalizeProjectPath(b);
}

/** Text shown inline for a ``project_read`` tool result (matches ProjectToolCallBlock). */
export function projectReadResultAsText(result: unknown): string {
  if (typeof result === 'string') return result;
  if (result !== undefined) return fmtJson(result);
  return '';
}

/**
 * Walk messages newest-first semantics by iterating in reverse; returns the latest
 * ``project_read`` body whose ``path`` matches ``selectedPath``.
 */
export function findLatestProjectReadContent(
  messages: Message[],
  selectedPath: string,
): string | null {
  const want = normalizeProjectPath(selectedPath);
  if (!want) return null;

  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (m?.role !== 'assistant' || !m.toolCalls?.length) continue;
    for (let j = m.toolCalls.length - 1; j >= 0; j -= 1) {
      const tc = m.toolCalls[j];
      if (!tc || tc.name !== 'project_read') continue;
      const args = tc.arguments ?? {};
      const p = strArg(args, 'path');
      if (!pathsMatch(p, selectedPath)) continue;
      if (tc.status !== 'success' && tc.status !== 'error') continue;
      const text = projectReadResultAsText(tc.result);
      if (text) return text;
    }
  }
  return null;
}

/** Latest ``project_write`` body for ``path`` (newest assistant message wins). */
export function findLatestProjectWriteContent(
  messages: Message[],
  selectedPath: string,
): string | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (m?.role !== 'assistant' || !m.toolCalls?.length) continue;
    for (let j = m.toolCalls.length - 1; j >= 0; j -= 1) {
      const tc = m.toolCalls[j];
      if (!tc || tc.name !== 'project_write') continue;
      const args = tc.arguments ?? {};
      const p = strArg(args, 'path');
      if (!pathsMatch(p, selectedPath)) continue;
      if (tc.status !== 'success' && tc.status !== 'error') continue;
      const body = strArg(args, 'content');
      return body || null;
    }
  }
  return null;
}

/** Latest ``project_edit`` ``new_string`` for ``path`` (snapshot after edit). */
export function findLatestProjectEditNewString(
  messages: Message[],
  selectedPath: string,
): string | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (m?.role !== 'assistant' || !m.toolCalls?.length) continue;
    for (let j = m.toolCalls.length - 1; j >= 0; j -= 1) {
      const tc = m.toolCalls[j];
      if (!tc || tc.name !== 'project_edit') continue;
      const args = tc.arguments ?? {};
      const p = strArg(args, 'path');
      if (!pathsMatch(p, selectedPath)) continue;
      if (tc.status !== 'success' && tc.status !== 'error') continue;
      const body = strArg(args, 'new_string');
      return body || null;
    }
  }
  return null;
}

export type PreviewKind = 'read' | 'write' | 'edit' | 'none';

/** Resolve preview text and its source for the workspace tab (priority: read > write > edit). */
export function resolvePathPreview(
  messages: Message[],
  selectedPath: string,
): { kind: PreviewKind; text: string } {
  const read = findLatestProjectReadContent(messages, selectedPath);
  if (read) return { kind: 'read', text: read };
  const write = findLatestProjectWriteContent(messages, selectedPath);
  if (write) return { kind: 'write', text: write };
  const edit = findLatestProjectEditNewString(messages, selectedPath);
  if (edit) return { kind: 'edit', text: edit };
  return { kind: 'none', text: '' };
}

export function isProjectFamilyTool(name: string): boolean {
  return (
    name === 'coding_agent' ||
    name.startsWith('project_') ||
    name.startsWith('coding_project_')
  );
}

export type PathOperation = 'read' | 'write' | 'edit' | 'execute' | 'unknown';

export interface PathWithOperation {
  path: string;
  operation: PathOperation;
}

function toolNameToOperation(name: string): PathOperation {
  if (name === 'project_read') return 'read';
  if (name === 'project_write') return 'write';
  if (name === 'project_edit' || name === 'project_apply_patch') return 'edit';
  if (name === 'project_shell' || name === 'code_execution' || name === 'coding_project_run')
    return 'execute';
  return 'unknown';
}

/**
 * Extract workspace / produced file paths from `code_execution` so the agent
 * workspace file list can populate when the session has no `project_*` tools.
 */
function collectPathsFromCodeExecution(
  tc: ToolCall,
  upsert: (raw: string, op: PathOperation) => void,
) {
  const args = tc.arguments ?? {};
  const staged = args.files;
  if (Array.isArray(staged)) {
    for (const item of staged) {
      if (item && typeof item === 'object') {
        const p = strArg(item as Record<string, unknown>, 'path');
        if (p) upsert(p, 'execute');
      }
    }
  }
  const res = tc.result;
  if (!res || typeof res !== 'object' || Array.isArray(res)) return;
  const r = res as Record<string, unknown>;
  const ws = r.workspace;
  if (typeof ws === 'string' && ws.trim()) upsert(ws, 'execute');

  const mergeList = (arr: unknown) => {
    if (!Array.isArray(arr)) return;
    for (const entry of arr) {
      if (entry && typeof entry === 'object') {
        const p = strArg(entry as Record<string, unknown>, 'path');
        if (p) upsert(p, 'execute');
      }
    }
  };
  mergeList(r.produced_files);
  mergeList(r.files);
}

/**
 * Unique sorted paths touched by project-family tools and `code_execution`
 * (workspace + produced files), each tagged with the most recent operation
 * type. When a path appears in multiple tools, the latest write/edit
 * operation wins over a read.
 */
export function collectProjectPathsWithOps(messages: Message[]): PathWithOperation[] {
  const map = new Map<string, PathOperation>();

  const upsert = (raw: string, op: PathOperation) => {
    const key = normalizeProjectPath(raw);
    if (!key) return;
    const prev = map.get(key);
    if (!prev || prev === 'read' || prev === 'unknown') {
      map.set(key, op);
    }
  };

  for (const m of messages) {
    if (m.role !== 'assistant') continue;
    for (const tc of m.toolCalls ?? []) {
      if (tc.name === 'code_execution') {
        collectPathsFromCodeExecution(tc, upsert);
        continue;
      }
      if (!isProjectFamilyTool(tc.name)) continue;
      const args = tc.arguments ?? {};
      const op = toolNameToOperation(tc.name);

      if (tc.name === 'coding_agent') {
        const pp = strArg(args, 'project_path');
        if (pp) upsert(pp, 'unknown');
        changedFilesList(tc.result).forEach((p) => upsert(p, 'edit'));
        parseActivity(tc.result).forEach((row) => {
          if (row.path) upsert(row.path, toolNameToOperation(row.tool ?? ''));
        });
      } else {
        const p = strArg(args, 'path') || strArg(args, 'project_path');
        if (p) upsert(p, op);
      }
    }
  }

  return [...map.entries()]
    .map(([path, operation]) => ({ path, operation }))
    .sort((a, b) => a.path.localeCompare(b.path));
}

/** Unique sorted paths (string-only, backward-compatible). */
export function collectProjectPathsFromMessages(messages: Message[]): string[] {
  return collectProjectPathsWithOps(messages).map((e) => e.path);
}

export interface AgentActivityEntry {
  tool: string;
  path?: string;
  operation: PathOperation;
  summary: string;
}

/** One-line human-readable label for an operation. */
function describeOp(tool: string, path?: string): string {
  const base = path ? path.split('/').pop() ?? path : '';
  switch (tool) {
    case 'project_read': return base ? `Read ${base}` : 'Read file';
    case 'project_write': return base ? `Wrote ${base}` : 'Wrote file';
    case 'project_edit': return base ? `Edited ${base}` : 'Edited file';
    case 'project_apply_patch': return base ? `Patched ${base}` : 'Applied patch';
    case 'project_shell': return 'Ran shell command';
    case 'code_execution': return 'Executed code';
    case 'coding_project_run': return 'Ran project';
    case 'coding_agent': return 'Coding agent task';
    default: return tool.replace(/_/g, ' ');
  }
}

/** Structured activity log from project-family tool calls for the Code tab summary. */
export function collectActivitySummary(messages: Message[]): AgentActivityEntry[] {
  const out: AgentActivityEntry[] = [];
  for (const m of messages) {
    if (m.role !== 'assistant') continue;
    for (const tc of m.toolCalls ?? []) {
      if (!isProjectFamilyTool(tc.name) && tc.name !== 'code_execution') continue;
      if (tc.status === 'pending') continue;
      const args = tc.arguments ?? {};
      const path = strArg(args, 'path') || strArg(args, 'project_path') || undefined;
      out.push({
        tool: tc.name,
        path,
        operation: toolNameToOperation(tc.name),
        summary: describeOp(tc.name, path),
      });
    }
  }
  return out;
}

/** Count of project-family tool calls in the thread (for tab badge). */
export function countProjectFamilyToolCalls(messages: Message[]): number {
  let n = 0;
  for (const m of messages) {
    if (m.role !== 'assistant') continue;
    for (const tc of m.toolCalls ?? []) {
      if (isProjectFamilyTool(tc.name)) n += 1;
    }
  }
  return n;
}

// ─── Coding project dev preview (loopback iframe) ─────────────────────────

export type CodingProjectRuntimeKindEnvelope = 'frontend' | 'fastapi' | 'python';

export interface CodingProjectRunPreviewInfo {
  projectId: string;
  /** Bind host from ``coding_project_run`` result. */
  host: string;
  /** Host the browser should use for ``http://…`` (maps ``0.0.0.0`` → ``127.0.0.1``). */
  iframeHost: string;
  port: number;
  previewUrl: string;
  runtimeKind: CodingProjectRuntimeKindEnvelope;
}

/** Normalize a ``coding_project_run`` tool result or POST ``/run`` response body. */
export function codingProjectRunPreviewInfoFromUnknown(
  result: unknown,
): CodingProjectRunPreviewInfo | null {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return null;
  const o = result as Record<string, unknown>;
  const projectId = typeof o.project_id === 'string' ? o.project_id.trim() : '';
  if (!projectId) return null;

  let port: number;
  if (typeof o.port === 'number' && Number.isFinite(o.port)) {
    port = o.port;
  } else if (typeof o.port === 'string' && o.port.trim()) {
    port = Number.parseInt(o.port.trim(), 10);
  } else {
    return null;
  }
  if (!Number.isFinite(port) || port <= 0 || port > 65535) return null;

  const hostRaw =
    typeof o.host === 'string' && o.host.trim().length > 0 ? o.host.trim() : '127.0.0.1';
  const iframeHost = hostRaw === '0.0.0.0' ? '127.0.0.1' : hostRaw;

  const previewUrl = typeof o.preview_url === 'string' ? o.preview_url : '';
  const runtimeKind: CodingProjectRuntimeKindEnvelope =
    o.runtime_kind === 'fastapi' ? 'fastapi' : o.runtime_kind === 'python' ? 'python' : 'frontend';

  return {
    projectId,
    host: hostRaw,
    iframeHost,
    port,
    previewUrl,
    runtimeKind,
  };
}

/**
 * HTTP URL for an embedded dev preview on the same machine as the browser
 * (not the token-gated API proxy).
 */
export function buildCodingProjectLoopbackPreviewUrl(info: CodingProjectRunPreviewInfo): string {
  const origin = `http://${info.iframeHost}:${info.port}`;
  return info.runtimeKind === 'fastapi'
    ? `${origin.replace(/\/$/, '')}/docs`
    : `${origin.replace(/\/$/, '')}/`;
}

/**
 * Map ``…/preview/?token=`` → ``…/preview/docs?token=`` for FastAPI Swagger UI.
 */
export function codingProjectPreviewPathWithDocs(previewUrl: string): string {
  const trimmed = previewUrl.trim();
  if (!trimmed) return trimmed;
  try {
    const u = new URL(
      trimmed,
      trimmed.startsWith('/') ? 'http://local.invalid' : undefined,
    );
    const path = u.pathname.replace(/\/+$/, '');
    if (path.endsWith('/preview')) {
      u.pathname = `${path}/docs`;
    }
    const out = u.pathname + u.search + u.hash;
    return trimmed.startsWith('/') ? out : u.href;
  } catch {
    return trimmed;
  }
}

/**
 * URL for an embedded coding-project iframe.
 *
 * Uses direct loopback on ``http:`` parents so Vite absolute paths (``/@vite/…``) keep working.
 * On ``https:`` parents, uses the signed API preview path to avoid mixed-content blocking.
 */
export function resolveCodingProjectPreviewUrlForEmbed(
  info: CodingProjectRunPreviewInfo,
  parentProtocol: string,
): string {
  const useProxy = parentProtocol === 'https:' && Boolean(info.previewUrl?.trim());
  if (useProxy) {
    let href = info.previewUrl!.trim();
    if (info.runtimeKind === 'fastapi') {
      href = codingProjectPreviewPathWithDocs(href);
    }
    return resolveCodingProjectPreviewHref(href);
  }
  return buildCodingProjectLoopbackPreviewUrl(info);
}

export function buildCodingProjectIframePreviewSrc(info: CodingProjectRunPreviewInfo): string {
  if (typeof window === 'undefined') {
    return buildCodingProjectLoopbackPreviewUrl(info);
  }
  return resolveCodingProjectPreviewUrlForEmbed(info, window.location.protocol);
}

/**
 * Latest successful ``coding_project_run`` in the thread (newest message / tool call wins).
 */
export function findLatestCodingProjectRunPreview(
  messages: Message[],
): CodingProjectRunPreviewInfo | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (!m || m.role !== 'assistant') continue;
    const tcs = m.toolCalls ?? [];
    for (let j = tcs.length - 1; j >= 0; j -= 1) {
      const tc = tcs[j];
      if (!tc || tc.name !== 'coding_project_run' || tc.status !== 'success') continue;
      const parsed = codingProjectRunPreviewInfoFromUnknown(tc.result);
      if (parsed) return parsed;
    }
  }
  return null;
}
