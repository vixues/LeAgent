import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  FolderOpen,
  FileText,
  Code,
  Image as ImageIcon,
  Library,
  Puzzle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useFolderList } from '@/hooks/useFolders';
import { useArtifactStore } from '@/stores/artifact';
import { useDocuments } from '@/hooks/useKnowledge';
import { buildKnowledgeChatToken } from '@/lib/knowledgeChatToken';

export interface MentionItem {
  id: string;
  label: string;
  type: 'folder' | 'artifact' | 'file' | 'knowledge' | 'skill';
  icon: React.ReactNode;
  insertText: string;
  /** For ``type === 'knowledge'``: token passed to ``pushFileRef`` / message. */
  knowledgeToken?: string;
  fileId?: string;
  /** For ``type === 'skill'``: manifest name + display label (slash palette parity). */
  skillName?: string;
  skillDisplayName?: string;
  /** Optional extra text for @ query filtering (e.g. skill description). */
  description?: string;
}

interface MentionPickerProps {
  open: boolean;
  query: string;
  /** Active skills (same shape as slash palette). */
  skills?: Array<{ name: string; display_name: string; description: string }>;
  onSelect: (item: MentionItem) => void;
  onClose: () => void;
  className?: string;
}

function getArtifactIcon(type: string) {
  switch (type) {
    case 'code':
      return <Code className="w-4 h-4" />;
    case 'image':
      return <ImageIcon className="w-4 h-4" />;
    default:
      return <FileText className="w-4 h-4" />;
  }
}

export function MentionPicker({
  open,
  query,
  skills = [],
  onSelect,
  onClose,
  className,
}: MentionPickerProps) {
  const { t } = useTranslation();
  const [activeIndex, setActiveIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const { data: rootFolders } = useFolderList(null);
  const artifacts = useArtifactStore((s) => s.artifacts);

  const qRaw = query.replace(/^@/, '').trim();
  const { data: docData, isFetching: docsFetching } = useDocuments({
    search: qRaw || undefined,
    page_size: 30,
    enabled: open,
  });

  const items: MentionItem[] = useMemo(() => {
    const out: MentionItem[] = [];

    skills.forEach((s) => {
      const label = s.display_name?.trim() || s.name;
      out.push({
        id: `skill-${s.name}`,
        label,
        type: 'skill',
        icon: <Puzzle className="w-4 h-4" />,
        insertText: '',
        skillName: s.name,
        skillDisplayName: s.display_name || s.name,
        description: s.description,
      });
    });

    (rootFolders ?? []).forEach((f) => {
      out.push({
        id: `folder-${f.id}`,
        label: f.name,
        type: 'folder',
        icon: <FolderOpen className="w-4 h-4" />,
        insertText: `@folder:${f.name} `,
      });
    });

    Object.values(artifacts).forEach((a) => {
      out.push({
        id: `artifact-${a.id}`,
        label: a.title,
        type: 'artifact',
        icon: getArtifactIcon(a.type),
        insertText: `@artifact:${a.title} `,
      });
    });

    (docData?.items ?? []).forEach((doc) => {
      const label = doc.original_name || doc.name;
      out.push({
        id: `knowledge-${doc.id}`,
        label,
        type: 'knowledge',
        icon: <Library className="w-4 h-4" />,
        insertText: '',
        fileId: doc.id,
        knowledgeToken: buildKnowledgeChatToken(label, doc.id),
      });
    });

    return out;
  }, [skills, rootFolders, artifacts, docData?.items]);

  const q = qRaw.toLowerCase();
  const filtered = items.filter((item) => {
    if (!q) return true;
    if (item.type === 'skill') {
      return (
        item.label.toLowerCase().includes(q) ||
        (item.skillName?.toLowerCase().includes(q) ?? false) ||
        (item.description?.toLowerCase().includes(q) ?? false)
      );
    }
    return item.label.toLowerCase().includes(q);
  });

  useEffect(() => {
    setActiveIndex(0);
  }, [query, items.length]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!open) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => (i + 1) % Math.max(1, filtered.length));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex(
          (i) => (i - 1 + filtered.length) % Math.max(1, filtered.length),
        );
      } else if (e.key === 'Enter' && filtered[activeIndex]) {
        e.preventDefault();
        onSelect(filtered[activeIndex]);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    },
    [open, filtered, activeIndex, onSelect, onClose],
  );

  useEffect(() => {
    if (!open) return;
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, handleKeyDown]);

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const item = list.children[activeIndex] as HTMLElement | undefined;
    item?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  if (!open) return null;

  if (filtered.length === 0 && docsFetching) {
    return (
      <div
        className={cn(
          'absolute bottom-full left-0 right-0 mb-2 z-50',
          'rounded-xl border border-border-subtle bg-surface shadow-soft',
          'max-h-[min(22rem,55vh)] px-3 py-6 text-center text-sm text-muted-foreground',
          'chat-palette-dialog',
          className,
        )}
        role="status"
      >
        {t('chat.mentionLoading', { defaultValue: 'Loading…' })}
      </div>
    );
  }

  if (filtered.length === 0) return null;

  const typeBadge = (item: MentionItem) => {
    if (item.type === 'knowledge') {
      return t('chat.composerRefs.knowledgeBadge', { defaultValue: 'Knowledge' });
    }
    if (item.type === 'skill') {
      return t('chat.composerRefs.skillBadge', { defaultValue: 'Skill' });
    }
    return item.type.charAt(0).toUpperCase() + item.type.slice(1);
  };

  return (
    <div
      className={cn(
        'absolute bottom-full left-0 right-0 mb-2 z-50',
        'rounded-xl border border-border-subtle bg-surface shadow-soft',
        'max-h-[min(22rem,55vh)] overflow-y-auto',
        'chat-palette-dialog',
        className,
      )}
      role="listbox"
      aria-label={t('chat.mention', { defaultValue: 'Mention' })}
    >
      <div className="sticky top-0 z-[1] border-b border-border-subtle/80 bg-surface/95 px-3 py-2 backdrop-blur-sm">
        <p className="text-[11px] font-semibold text-muted-foreground-tertiary uppercase tracking-wider">
          {t('chat.mentions', { defaultValue: 'Mentions' })}
        </p>
      </div>
      <div
        ref={listRef}
        className="grid grid-cols-1 gap-2 p-2 sm:grid-cols-2 lg:grid-cols-3"
      >
        {filtered.map((item, idx) => {
          const isActive = idx === activeIndex;
          const desc =
            item.type === 'skill' && item.description?.trim()
              ? item.description.trim()
              : null;

          return (
            <button
              key={item.id}
              type="button"
              role="option"
              aria-selected={isActive}
              onClick={() => onSelect(item)}
              onMouseEnter={() => setActiveIndex(idx)}
              className={cn(
                'flex min-h-[4.25rem] flex-col rounded-xl border p-3 text-left transition-all outline-none',
                'focus-visible:ring-2 focus-visible:ring-primary-500/40',
                isActive
                  ? 'border-primary-400 bg-primary-50 shadow-sm ring-2 ring-primary-500/25 dark:border-primary-600 dark:bg-primary-900/25'
                  : 'border-border-subtle bg-surface-sunken/50 hover:border-border-strong hover:bg-surface-sunken',
              )}
            >
              <div className="flex min-w-0 flex-1 gap-2.5">
                <span
                  className={cn(
                    'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
                    isActive
                      ? 'bg-primary-500/15 text-primary-600 dark:text-primary-400'
                      : 'bg-muted/60 text-muted-foreground',
                  )}
                >
                  {item.icon}
                </span>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="text-sm font-semibold leading-snug text-foreground line-clamp-2">
                    {item.label}
                  </div>
                  <span
                    className={cn(
                      'inline-flex max-w-full rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                      isActive
                        ? 'bg-primary-500/15 text-primary-700 dark:text-primary-300'
                        : 'bg-muted text-muted-foreground',
                    )}
                  >
                    {typeBadge(item)}
                  </span>
                  {desc ? (
                    <p className="text-[11px] leading-relaxed text-muted-foreground line-clamp-2">
                      {desc}
                    </p>
                  ) : null}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
