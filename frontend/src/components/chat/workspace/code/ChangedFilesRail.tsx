import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getFileExtensionIcon } from '@/components/chat/workspace/artifactIcon';
import type { TouchedFile } from '@/lib/agentSessionEvents';
import { eventKindMeta } from './eventMeta';

interface ChangedFilesRailProps {
  files: TouchedFile[];
  onSelect: (eventId: string) => void;
}

export function ChangedFilesRail({ files, onSelect }: ChangedFilesRailProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);

  if (files.length === 0) return null;

  return (
    <div className="shrink-0 overflow-hidden rounded-lg border border-border-subtle/50 bg-surface-sunken/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface/40"
      >
        {open ? (
          <ChevronDown className="size-3 shrink-0 text-muted-foreground" aria-hidden />
        ) : (
          <ChevronRight className="size-3 shrink-0 text-muted-foreground" aria-hidden />
        )}
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('chat.workspace.agent.changedFilesTitle', { defaultValue: 'Files touched' })}
        </span>
        <span className="ml-auto text-[10px] tabular-nums text-muted-foreground/60">
          {files.length}
        </span>
      </button>
      {open && (
        <div className="flex max-h-[22vh] flex-wrap gap-1.5 overflow-y-auto border-t border-border-subtle/40 p-2">
          {files.map((file) => {
            const meta = eventKindMeta(file.kind);
            return (
              <button
                key={file.path}
                type="button"
                onClick={() => onSelect(file.eventId)}
                title={file.path}
                className={cn(
                  'flex max-w-full items-center gap-1.5 rounded-md border border-border-subtle/40 bg-surface/40 px-2 py-1 text-left text-[11px] transition-colors',
                  'hover:border-primary/30 hover:bg-surface',
                )}
              >
                <span className="shrink-0">{getFileExtensionIcon(file.label)}</span>
                <span className="min-w-0 truncate font-mono text-muted-foreground">
                  {file.label}
                </span>
                <span
                  className={cn(
                    'shrink-0 rounded px-1 py-px text-[8px] font-bold uppercase leading-none',
                    meta.accent,
                  )}
                >
                  {meta.badge}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
