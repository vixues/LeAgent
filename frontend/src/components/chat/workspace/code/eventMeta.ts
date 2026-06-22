/**
 * Single per-kind presentation map for agent session events — icon, accent
 * color, short uppercase op badge, and an i18n verb key. Replaces the
 * `OP_ICONS` / `OP_COLORS` / `KIND_COLORS` triplication that previously lived
 * across the workspace components.
 */
import {
  Brackets,
  Eye,
  FilePen,
  FilePlus2,
  FileText,
  GitCompareArrows,
  LayoutTemplate,
  Play,
  Server,
  Terminal,
  type LucideIcon,
} from 'lucide-react';
import type { AgentEventKind } from '@/lib/agentSessionEvents';

export interface EventKindMeta {
  icon: LucideIcon;
  /** Short uppercase op badge, e.g. `R` `W` `E`. */
  badge: string;
  /** Accent classes for icon / badge tint (badge bg + text). */
  accent: string;
  /** i18n key (under `chat.workspace.agent.kinds`) for the CLI verb. */
  labelKey: string;
  /** Default verb if the i18n key is missing. */
  verb: string;
}

export const EVENT_KIND_META: Record<AgentEventKind, EventKindMeta> = {
  read: {
    icon: Eye,
    badge: 'R',
    accent: 'bg-sky-500/15 text-sky-600 dark:text-sky-400',
    labelKey: 'chat.workspace.agent.kinds.read',
    verb: 'Read',
  },
  write: {
    icon: FilePlus2,
    badge: 'W',
    accent: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
    labelKey: 'chat.workspace.agent.kinds.write',
    verb: 'Write',
  },
  edit: {
    icon: FilePen,
    badge: 'E',
    accent: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
    labelKey: 'chat.workspace.agent.kinds.edit',
    verb: 'Edit',
  },
  patch: {
    icon: GitCompareArrows,
    badge: 'P',
    accent: 'bg-cyan-500/15 text-cyan-600 dark:text-cyan-400',
    labelKey: 'chat.workspace.agent.kinds.patch',
    verb: 'Patch',
  },
  shell: {
    icon: Terminal,
    badge: '$',
    accent: 'bg-zinc-500/15 text-zinc-600 dark:text-zinc-400',
    labelKey: 'chat.workspace.agent.kinds.shell',
    verb: 'Shell',
  },
  code_exec: {
    icon: Play,
    badge: 'X',
    accent: 'bg-violet-500/15 text-violet-600 dark:text-violet-400',
    labelKey: 'chat.workspace.agent.kinds.code_exec',
    verb: 'Run',
  },
  project_run: {
    icon: Server,
    badge: '↑',
    accent: 'bg-teal-500/15 text-teal-600 dark:text-teal-400',
    labelKey: 'chat.workspace.agent.kinds.project_run',
    verb: 'Serve',
  },
  doc_gen: {
    icon: FileText,
    badge: 'D',
    accent: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
    labelKey: 'chat.workspace.agent.kinds.doc_gen',
    verb: 'Doc',
  },
  canvas: {
    icon: LayoutTemplate,
    badge: 'C',
    accent: 'bg-fuchsia-500/15 text-fuchsia-600 dark:text-fuchsia-400',
    labelKey: 'chat.workspace.agent.kinds.canvas',
    verb: 'Canvas',
  },
  nested_agent: {
    icon: Brackets,
    badge: '»',
    accent: 'bg-indigo-500/15 text-indigo-600 dark:text-indigo-400',
    labelKey: 'chat.workspace.agent.kinds.nested_agent',
    verb: 'Subagent',
  },
};

export function eventKindMeta(kind: AgentEventKind): EventKindMeta {
  return EVENT_KIND_META[kind] ?? EVENT_KIND_META.read;
}
