import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Trash2,
  Plus,
  PanelRight,
  RotateCcw,
  Sparkles,
  Paperclip,
  Puzzle,
} from 'lucide-react';
import { cn } from '@/lib/utils';

export interface SlashCommand {
  id: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  command: string;
}

export interface SlashPaletteSkillItem {
  name: string;
  display_name: string;
  description: string;
}

export type SlashPaletteSelection =
  | { kind: 'builtin'; cmd: SlashCommand }
  | { kind: 'skill'; name: string; display_name: string };

const BUILTIN_COMMANDS: SlashCommand[] = [
  {
    id: 'new',
    label: 'New Chat',
    description: 'Start a new conversation',
    icon: <Plus className="w-4 h-4" />,
    command: '/new',
  },
  {
    id: 'clear',
    label: 'Clear Messages',
    description: 'Clear current conversation',
    icon: <Trash2 className="w-4 h-4" />,
    command: '/clear',
  },
  {
    id: 'workspace',
    label: 'Toggle Workspace',
    description: 'Open or close workspace panel',
    icon: <PanelRight className="w-4 h-4" />,
    command: '/workspace',
  },
  {
    id: 'regenerate',
    label: 'Regenerate',
    description: 'Regenerate last response',
    icon: <RotateCcw className="w-4 h-4" />,
    command: '/regenerate',
  },
  {
    id: 'model',
    label: 'Switch Model',
    description: 'Change the active model',
    icon: <Sparkles className="w-4 h-4" />,
    command: '/model',
  },
  {
    id: 'attach',
    label: 'Attach File',
    description: 'Attach a file to your message',
    icon: <Paperclip className="w-4 h-4" />,
    command: '/attach',
  },
];

interface SlashCommandPaletteProps {
  open: boolean;
  query: string;
  skills?: SlashPaletteSkillItem[];
  onSelect: (selection: SlashPaletteSelection) => void;
  onClose: () => void;
  className?: string;
}

export function SlashCommandPalette({
  open,
  query,
  skills = [],
  onSelect,
  onClose,
  className,
}: SlashCommandPaletteProps) {
  const { t } = useTranslation();
  const [activeIndex, setActiveIndex] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { filteredCmds, filteredSkills } = useMemo(() => {
    const q = query.replace(/^\//, '').toLowerCase();
    const match = (s: string) => {
      if (!q) return true;
      return s.toLowerCase().includes(q);
    };
    const filteredCmds = BUILTIN_COMMANDS.filter(
      (cmd) => match(cmd.label) || match(cmd.command),
    );
    const filteredSkills = skills.filter(
      (s) =>
        match(s.display_name) || match(s.name) || match(s.description),
    );
    return { filteredCmds, filteredSkills };
  }, [query, skills]);

  const flatLength = filteredCmds.length + filteredSkills.length;

  useEffect(() => {
    setActiveIndex(0);
  }, [query, filteredCmds.length, filteredSkills.length]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!open || flatLength === 0) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => (i + 1) % flatLength);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((i) => (i - 1 + flatLength) % flatLength);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (activeIndex < filteredCmds.length) {
          onSelect({ kind: 'builtin', cmd: filteredCmds[activeIndex]! });
        } else {
          const sk = filteredSkills[activeIndex - filteredCmds.length];
          if (sk) {
            onSelect({
              kind: 'skill',
              name: sk.name,
              display_name: sk.display_name,
            });
          }
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    },
    [
      open,
      flatLength,
      activeIndex,
      filteredCmds,
      filteredSkills,
      onSelect,
      onClose,
    ],
  );

  useEffect(() => {
    if (!open) return;
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, handleKeyDown]);

  useEffect(() => {
    if (!open || flatLength === 0) return;
    const root = scrollRef.current;
    if (!root) return;
    const options = root.querySelectorAll<HTMLElement>('[role="option"]');
    const el = options[activeIndex];
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex, open, flatLength]);

  if (!open || flatLength === 0) return null;

  const sectionHeaderClass =
    'px-3 pt-2 pb-1 text-[11px] font-semibold text-muted-foreground-tertiary uppercase tracking-wider';

  return (
    <div
      className={cn(
        'absolute bottom-full left-0 right-0 mb-2 z-50',
        'rounded-xl border border-border-subtle bg-surface shadow-soft',
        'max-h-64 overflow-y-auto',
        'chat-palette-dialog',
        className,
      )}
      role="listbox"
      aria-label={t('chat.slashCommand', {
        defaultValue: 'Slash commands',
      })}
    >
      <div ref={scrollRef}>
        {filteredCmds.length > 0 && (
          <>
            <div className={sectionHeaderClass}>
              {t('chat.commands', { defaultValue: 'Commands' })}
            </div>
            <div className="p-1 pt-0">
              {filteredCmds.map((cmd, idx) => {
                const flatIdx = idx;
                return (
                  <button
                    key={cmd.id}
                    type="button"
                    role="option"
                    aria-selected={flatIdx === activeIndex}
                    onClick={() => onSelect({ kind: 'builtin', cmd })}
                    onMouseEnter={() => setActiveIndex(flatIdx)}
                    className={cn(
                      'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors',
                      flatIdx === activeIndex
                        ? 'bg-primary-50 dark:bg-primary-900/20 text-foreground'
                        : 'text-muted-foreground hover:bg-surface-sunken',
                    )}
                  >
                    <span
                      className={cn(
                        'flex-shrink-0',
                        flatIdx === activeIndex
                          ? 'text-primary-600 dark:text-primary-400'
                          : 'text-muted-foreground-tertiary',
                      )}
                    >
                      {cmd.icon}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium">{cmd.label}</div>
                      <div className="text-xs text-muted-foreground-tertiary">
                        {cmd.description}
                      </div>
                    </div>
                    <span className="text-[11px] text-muted-foreground-tertiary font-mono">
                      {cmd.command}
                    </span>
                  </button>
                );
              })}
            </div>
          </>
        )}

        {filteredSkills.length > 0 && (
          <>
            <div className={sectionHeaderClass}>
              {t('chat.skillsInSlash', { defaultValue: 'Skills' })}
            </div>
            <div className="p-1 pt-0">
              {filteredSkills.map((sk, j) => {
                const flatIdx = filteredCmds.length + j;
                return (
                  <button
                    key={`skill-${sk.name}`}
                    type="button"
                    role="option"
                    aria-selected={flatIdx === activeIndex}
                    onClick={() =>
                      onSelect({
                        kind: 'skill',
                        name: sk.name,
                        display_name: sk.display_name,
                      })
                    }
                    onMouseEnter={() => setActiveIndex(flatIdx)}
                    className={cn(
                      'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors',
                      flatIdx === activeIndex
                        ? 'bg-primary-50 dark:bg-primary-900/20 text-foreground'
                        : 'text-muted-foreground hover:bg-surface-sunken',
                    )}
                  >
                    <span
                      className={cn(
                        'flex-shrink-0',
                        flatIdx === activeIndex
                          ? 'text-primary-600 dark:text-primary-400'
                          : 'text-muted-foreground-tertiary',
                      )}
                    >
                      <Puzzle className="w-4 h-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium">{sk.display_name}</div>
                      <div className="text-xs text-muted-foreground-tertiary line-clamp-2">
                        {sk.description}
                      </div>
                    </div>
                    <span className="text-[11px] text-muted-foreground-tertiary font-mono shrink-0">
                      {sk.name}
                    </span>
                  </button>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
