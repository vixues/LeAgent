import type { Message } from '@/types/chat';

export interface AgentTerminalLogEntry {
  id: string;
  toolName: string;
  stdout: string;
  stderr: string;
  stdoutTruncated: boolean;
  stderrTruncated: boolean;
}

const TERMINAL_TOOLS = new Set([
  'project_shell',
  'code_execution',
  'coding_project_run',
]);

interface StdioPayload {
  stdout: string;
  stderr: string;
  stdoutTruncated: boolean;
  stderrTruncated: boolean;
}

function stdoutStderrFromResult(
  result: unknown,
  toolName: string,
): StdioPayload | null {
  if (!result || typeof result !== 'object' || Array.isArray(result)) {
    return TERMINAL_TOOLS.has(toolName) ? { stdout: '', stderr: '', stdoutTruncated: false, stderrTruncated: false } : null;
  }
  const r = result as Record<string, unknown>;
  const hasStdout = 'stdout' in r;
  const hasStderr = 'stderr' in r;
  if (!hasStdout && !hasStderr) {
    return TERMINAL_TOOLS.has(toolName) ? { stdout: '', stderr: '', stdoutTruncated: false, stderrTruncated: false } : null;
  }
  return {
    stdout: typeof r.stdout === 'string' ? r.stdout : '',
    stderr: typeof r.stderr === 'string' ? r.stderr : '',
    stdoutTruncated: r.stdout_truncated === true,
    stderrTruncated: r.stderr_truncated === true,
  };
}

/** Aggregate shell / script stdout+stderr from session messages for the workspace terminal panel. */
export function collectAgentTerminalLogs(messages: Message[]): AgentTerminalLogEntry[] {
  const out: AgentTerminalLogEntry[] = [];
  let seq = 0;
  for (const m of messages) {
    if (m.role !== 'assistant' || !m.toolCalls?.length) continue;
    for (const tc of m.toolCalls) {
      if (!tc || tc.status === 'pending') continue;
      const name = tc.name;
      const payload = stdoutStderrFromResult(tc.result, name);
      if (!payload) continue;
      if (!TERMINAL_TOOLS.has(name) && !payload.stdout && !payload.stderr) continue;
      seq += 1;
      out.push({
        id: `${m.id}-${tc.id}-${seq}`,
        toolName: name,
        stdout: payload.stdout,
        stderr: payload.stderr,
        stdoutTruncated: payload.stdoutTruncated,
        stderrTruncated: payload.stderrTruncated,
      });
    }
  }
  return out;
}
