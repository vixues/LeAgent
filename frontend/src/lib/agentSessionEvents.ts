/**
 * Normalized agent-session event model — the single source of truth for the
 * workspace "Code" tab (Claude Code CLI-style execution harness).
 *
 * {@link collectAgentSessionEvents} folds every code-bearing tool call
 * (`project_*`, `code_execution`, `coding_project_run`, doc processors,
 * `canvas_publish`, `coding_agent`) plus the live sub-agent stream into a flat,
 * chronological list of {@link AgentSessionEvent}. The timeline, changed-files
 * rail, summary header, and terminal dock all derive from this one list, so the
 * previous five overlapping selectors / panels collapse into a single pipeline.
 */
import type { AgentImageArtifact } from '@/lib/agentImageArtifacts';
import {
  formatAgentPathLabel,
  isCodeExecWorkspaceDir,
} from '@/lib/agentPathDisplay';
import { pickCanvasHtmlPreview } from '@/lib/canvasStreamPreview';
import { pickCodeExecutionSourcePreview } from '@/lib/codeExecutionStreamPreview';
import {
  extractDocProcessorPath,
  extractDocProcessorPreviewText,
  isDocProcessorTool,
  languageForDocProcessorPreview,
} from '@/lib/docProcessorStreamPreview';
import { pickJsonStringField } from '@/lib/jsonStreamField';
import {
  extractNestedPreviewText,
  languageForNestedPreview,
} from '@/lib/nestedAgentStreamPreview';
import {
  changedFilesList,
  normalizeProjectPath,
  projectReadResultAsText,
  strArg,
} from '@/lib/projectToolEnvelope';
import type { CodeArtifactEntry } from '@/stores/codeArtifact';
import { extToLanguage } from '@/pages/FolderPage/project/extToLanguage';
import type { Message, NestedAgentPreviewState, ToolCall } from '@/types/chat';

export type AgentEventKind =
  | 'read'
  | 'write'
  | 'edit'
  | 'patch'
  | 'shell'
  | 'code_exec'
  | 'project_run'
  | 'doc_gen'
  | 'canvas'
  | 'nested_agent';

export type AgentEventStatus = 'pending' | 'running' | 'success' | 'error';

export interface AgentSessionEvent {
  id: string;
  kind: AgentEventKind;
  status: AgentEventStatus;
  /** Monotonic ordering key (message index × 1000 + tool-call index). */
  order: number;
  /** Whether tool arguments are still streaming (live, tail-scrolled). */
  streaming: boolean;
  /** Primary subject path (file / workspace), when applicable. */
  path?: string;
  /** Display label — file basename or a synthesized command/title. */
  label: string;
  /** highlight.js language token for code rendering. */
  language: string;
  /** Code body (read/write/patch/canvas/doc_gen/code_exec source). */
  code?: string;
  /** Before/after pair for `edit` events. */
  diff?: { before: string; after: string };
  stdout?: string;
  stderr?: string;
  stdoutTruncated?: boolean;
  stderrTruncated?: boolean;
  images?: AgentImageArtifact[];
  /** Paths reported changed by a `coding_agent` sub-task. */
  changedFiles?: string[];
  previewUrl?: string;
  port?: string;
  durationMs?: number;
  /** `true` ok, `false` syntax errors found, `null`/`undefined` unknown. */
  syntaxValid?: boolean | null;
  artifactId?: string;
  errorText?: string;
  /** LLM tool_call id (correlates with live `tool_output_delta` chunks). */
  toolCallId?: string;
}

export interface SessionEventSummary {
  total: number;
  fileCount: number;
  readCount: number;
  execCount: number;
  errorCount: number;
  runningCount: number;
  totalDurationMs: number;
}

export interface TouchedFile {
  path: string;
  label: string;
  kind: AgentEventKind;
  status: AgentEventStatus;
  order: number;
  eventId: string;
}

const STREAMING_STATES: ReadonlySet<ToolCall['status']> = new Set([
  'running',
  'pending',
]);

/** Tools whose stdio belongs in the terminal dock. */
const TERMINAL_KINDS: ReadonlySet<AgentEventKind> = new Set([
  'shell',
  'code_exec',
  'project_run',
]);

/** Kinds that mutate a file on disk (for the "files changed" summary). */
const MUTATING_KINDS: ReadonlySet<AgentEventKind> = new Set([
  'write',
  'edit',
  'patch',
  'doc_gen',
]);

function str(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim().length > 0 ? value : undefined;
}

function mapStatus(status: ToolCall['status']): AgentEventStatus {
  if (status === 'success') return 'success';
  if (status === 'error') return 'error';
  if (status === 'pending') return 'pending';
  return 'running'; // running | awaiting_user
}

interface Stdio {
  stdout?: string;
  stderr?: string;
  stdoutTruncated?: boolean;
  stderrTruncated?: boolean;
}

function stdioFromResult(result: unknown): Stdio {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return {};
  const r = result as Record<string, unknown>;
  return {
    stdout: typeof r.stdout === 'string' ? r.stdout : undefined,
    stderr: typeof r.stderr === 'string' ? r.stderr : undefined,
    stdoutTruncated: r.stdout_truncated === true,
    stderrTruncated: r.stderr_truncated === true,
  };
}

function imagesFromResult(
  result: unknown,
  messageId: string,
  toolCallId: string,
): AgentImageArtifact[] {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return [];
  const arr = (result as Record<string, unknown>).managed_artifacts;
  if (!Array.isArray(arr)) return [];
  const out: AgentImageArtifact[] = [];
  const seen = new Set<string>();
  for (const raw of arr) {
    if (!raw || typeof raw !== 'object') continue;
    const e = raw as Record<string, unknown>;
    const mime = str(e.content_type) ?? str(e.mime) ?? '';
    if (!mime.toLowerCase().startsWith('image/')) continue;
    const previewUrl = str(e.preview_url) ?? str(e.previewUrl);
    if (!previewUrl) continue;
    const id = str(e.id) ?? `${messageId}-${toolCallId}-${previewUrl}`;
    if (seen.has(id)) continue;
    seen.add(id);
    out.push({
      id,
      mime,
      previewUrl,
      downloadUrl: str(e.download_url) ?? str(e.downloadUrl),
      sha256: str(e.sha256),
      fileName: str(e.filename) ?? str(e.name),
    });
  }
  return out;
}

function syntaxValidFromResult(result: unknown): boolean | null {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return null;
  const diags = (result as Record<string, unknown>).syntax_diagnostics;
  if (Array.isArray(diags) && diags.length > 0) return false;
  return null;
}

function artifactIdFromResult(result: unknown): string | undefined {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return undefined;
  return str((result as Record<string, unknown>).artifact_id);
}

function shellCommandLabel(args: Record<string, unknown>): string {
  const command = strArg(args, 'command');
  if (command) return command;
  const argv = args.argv;
  if (Array.isArray(argv)) {
    return argv.filter((x): x is string => typeof x === 'string').join(' ');
  }
  return '';
}

function buildEvent(
  messageId: string,
  messageIndex: number,
  toolIndex: number,
  tc: ToolCall,
): AgentSessionEvent | null {
  const name = tc.name;
  const args = tc.arguments ?? {};
  const raw = typeof tc.argumentsRaw === 'string' ? tc.argumentsRaw : '';
  const streaming = STREAMING_STATES.has(tc.status);
  const status = mapStatus(tc.status);
  const order = messageIndex * 1000 + toolIndex;
  const id = `${messageId}-${tc.id || toolIndex}`;

  const base = {
    id,
    order,
    status,
    streaming,
    durationMs: tc.duration_ms,
    errorText: str(tc.error),
    toolCallId: tc.id || undefined,
  };

  if (name === 'code_execution') {
    const source = pickCodeExecutionSourcePreview(raw, args) || strArg(args, 'source');
    const io = stdioFromResult(tc.result);
    return {
      ...base,
      kind: 'code_exec',
      label: 'python',
      language: 'python',
      code: source,
      ...io,
      images: imagesFromResult(tc.result, messageId, tc.id),
      artifactId: artifactIdFromResult(tc.result),
      syntaxValid: syntaxValidFromResult(tc.result),
    };
  }

  if (name === 'project_shell') {
    const command = shellCommandLabel(args);
    return {
      ...base,
      kind: 'shell',
      label: command || 'shell',
      language: 'bash',
      code: command || undefined,
      ...stdioFromResult(tc.result),
    };
  }

  if (name === 'coding_project_run') {
    const result = tc.result;
    let previewUrl: string | undefined;
    let port: string | undefined;
    if (result && typeof result === 'object' && !Array.isArray(result)) {
      const o = result as Record<string, unknown>;
      previewUrl = str(o.preview_url);
      if (typeof o.port === 'number') port = String(o.port);
      else port = str(o.port);
    }
    return {
      ...base,
      kind: 'project_run',
      label: 'dev server',
      language: 'bash',
      previewUrl,
      port,
      ...stdioFromResult(tc.result),
    };
  }

  if (name === 'project_read') {
    const path = strArg(args, 'path');
    return {
      ...base,
      kind: 'read',
      path: path || undefined,
      label: path ? formatAgentPathLabel(path) : 'read',
      language: extToLanguage(path),
      code: projectReadResultAsText(tc.result),
    };
  }

  if (name === 'project_write') {
    const path = strArg(args, 'path');
    const content = streaming
      ? pickJsonStringField('content', raw, args)
      : strArg(args, 'content') || pickJsonStringField('content', raw, args);
    return {
      ...base,
      kind: 'write',
      path: path || undefined,
      label: path ? formatAgentPathLabel(path) : 'write',
      language: extToLanguage(path),
      code: content,
    };
  }

  if (name === 'project_edit') {
    const path = strArg(args, 'path');
    const after = streaming
      ? pickJsonStringField('new_string', raw, args)
      : strArg(args, 'new_string');
    return {
      ...base,
      kind: 'edit',
      path: path || undefined,
      label: path ? formatAgentPathLabel(path) : 'edit',
      language: extToLanguage(path),
      diff: { before: strArg(args, 'old_string'), after },
    };
  }

  if (name === 'project_apply_patch') {
    const path = strArg(args, 'path');
    const diff = streaming
      ? pickJsonStringField('diff', raw, args)
      : strArg(args, 'diff') || pickJsonStringField('diff', raw, args);
    return {
      ...base,
      kind: 'patch',
      path: path || undefined,
      label: path ? formatAgentPathLabel(path) : 'patch',
      language: 'diff',
      code: diff,
    };
  }

  if (isDocProcessorTool(name)) {
    const path = strArg(args, 'file_path') || extractDocProcessorPath(raw, args);
    const fromArgs =
      name === 'text_processor' ? strArg(args, 'data') : strArg(args, 'content');
    const fromStream = extractDocProcessorPreviewText(name, raw, args);
    const code = streaming ? fromStream : fromArgs || fromStream;
    return {
      ...base,
      kind: 'doc_gen',
      path: path || undefined,
      label: path ? formatAgentPathLabel(path) : 'document',
      language: languageForDocProcessorPreview(path, name),
      code,
    };
  }

  if (name === 'canvas_publish') {
    return {
      ...base,
      kind: 'canvas',
      label: 'canvas',
      language: 'html',
      code: pickCanvasHtmlPreview(raw, args),
    };
  }

  if (name === 'coding_agent') {
    const prompt = strArg(args, 'prompt');
    return {
      ...base,
      kind: 'nested_agent',
      label: 'coding agent',
      language: 'text',
      code: prompt.length > 600 ? `${prompt.slice(0, 600)}…` : prompt,
      changedFiles: changedFilesList(tc.result),
    };
  }

  return null;
}

function buildNestedPreviewEvent(
  preview: NestedAgentPreviewState,
  order: number,
): AgentSessionEvent | null {
  const partial = preview.argumentsPartial;
  const path = str(partial?.path) ?? str(partial?.file_path);
  const code = extractNestedPreviewText(preview.toolName, preview.argumentsRaw, partial);
  if (!code) return null;
  return {
    id: `nested-live-${preview.parentToolCallId}`,
    kind: 'nested_agent',
    status: 'running',
    streaming: true,
    order,
    path,
    label: preview.toolName,
    language: languageForNestedPreview(preview.toolName, partial),
    code,
  };
}

function enrichSyntax(
  events: AgentSessionEvent[],
  codeArtifacts: CodeArtifactEntry[],
): void {
  const byPath = new Map<string, boolean | null | undefined>();
  for (const entry of codeArtifacts) {
    if (!entry.targetPath) continue;
    byPath.set(normalizeProjectPath(entry.targetPath), entry.syntaxValid);
  }
  if (byPath.size === 0) return;
  for (const ev of events) {
    if (ev.syntaxValid !== undefined && ev.syntaxValid !== null) continue;
    if (!ev.path) continue;
    const flag = byPath.get(normalizeProjectPath(ev.path));
    if (flag !== undefined) ev.syntaxValid = flag;
  }
}

/**
 * Build the chronological agent event timeline from session messages, the code
 * artifact store, and the optional live sub-agent stream.
 */
export function collectAgentSessionEvents(
  messages: Message[],
  codeArtifacts: CodeArtifactEntry[] = [],
  nestedPreview?: NestedAgentPreviewState | null,
): AgentSessionEvent[] {
  const events: AgentSessionEvent[] = [];
  messages.forEach((m, mi) => {
    if (m.role !== 'assistant' || !m.toolCalls?.length) return;
    m.toolCalls.forEach((tc, ti) => {
      if (!tc) return;
      const ev = buildEvent(m.id, mi, ti, tc);
      if (ev) events.push(ev);
    });
  });

  if (codeArtifacts.length > 0) enrichSyntax(events, codeArtifacts);

  if (nestedPreview) {
    const ev = buildNestedPreviewEvent(nestedPreview, (messages.length + 1) * 1000);
    if (ev) events.push(ev);
  }

  return events;
}

/** Aggregate header counts (files changed, reads, executions, errors, duration). */
export function summarizeSessionEvents(
  events: AgentSessionEvent[],
): SessionEventSummary {
  const changedPaths = new Set<string>();
  let readCount = 0;
  let execCount = 0;
  let errorCount = 0;
  let runningCount = 0;
  let totalDurationMs = 0;

  for (const ev of events) {
    if (MUTATING_KINDS.has(ev.kind) && ev.path) {
      changedPaths.add(normalizeProjectPath(ev.path));
    }
    if (ev.kind === 'read') readCount += 1;
    if (TERMINAL_KINDS.has(ev.kind)) execCount += 1;
    if (ev.status === 'error') errorCount += 1;
    if (ev.status === 'running' || ev.status === 'pending') runningCount += 1;
    if (typeof ev.durationMs === 'number') totalDurationMs += ev.durationMs;
  }

  return {
    total: events.length,
    fileCount: changedPaths.size,
    readCount,
    execCount,
    errorCount,
    runningCount,
    totalDurationMs,
  };
}

/**
 * Unique files the agent touched, latest event per path wins. Used by the
 * changed-files rail for jump-to-event navigation.
 */
export function collectTouchedFiles(events: AgentSessionEvent[]): TouchedFile[] {
  const byPath = new Map<string, TouchedFile>();
  for (const ev of events) {
    if (!ev.path) continue;
    if (isCodeExecWorkspaceDir(ev.path)) continue;
    const key = normalizeProjectPath(ev.path);
    const prev = byPath.get(key);
    if (!prev || ev.order >= prev.order) {
      byPath.set(key, {
        path: ev.path,
        label: ev.label,
        kind: ev.kind,
        status: ev.status,
        order: ev.order,
        eventId: ev.id,
      });
    }
  }
  return [...byPath.values()].sort((a, b) => a.path.localeCompare(b.path));
}

/** Command-style events (shell / code-exec / dev-server) for the terminal dock. */
export function collectTerminalEvents(
  events: AgentSessionEvent[],
): AgentSessionEvent[] {
  return events.filter((ev) => TERMINAL_KINDS.has(ev.kind));
}

/**
 * Flatten every produced media artifact across the session into a single,
 * deduplicated, chronologically-ordered list. Powers the persistent artifacts
 * gallery, so previews no longer depend on a row being expanded.
 */
export function collectArtifacts(
  events: AgentSessionEvent[],
): AgentImageArtifact[] {
  const out: AgentImageArtifact[] = [];
  const seen = new Set<string>();
  for (const ev of [...events].sort((a, b) => a.order - b.order)) {
    if (!ev.images?.length) continue;
    for (const img of ev.images) {
      if (seen.has(img.id)) continue;
      seen.add(img.id);
      out.push(img);
    }
  }
  return out;
}
