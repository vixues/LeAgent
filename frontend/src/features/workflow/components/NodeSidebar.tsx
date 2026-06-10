import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronRight, Search } from 'lucide-react';

import { cn } from '@/lib/utils';

import type { NodeDefinition, ObjectInfo } from '../graph/objectInfo';

interface NodeSidebarProps {
  registry: ObjectInfo;
  collapsed?: boolean;
  onAdd: (def: NodeDefinition) => void;
}

/** Node catalog grouped by category, with drag-to-canvas + click-to-add. */
export function NodeSidebar({ registry, collapsed, onAdd }: NodeSidebarProps) {
  const { t } = useTranslation('workflows');
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState<Record<string, boolean>>({});

  const grouped = useMemo(() => {
    const q = query.trim().toLowerCase();
    const byCat = new Map<string, NodeDefinition[]>();
    for (const def of Object.values(registry.definitions)) {
      if (def.deprecated) continue;
      if (
        q &&
        !def.displayName.toLowerCase().includes(q) &&
        !def.type.toLowerCase().includes(q) &&
        !def.category.toLowerCase().includes(q)
      ) {
        continue;
      }
      const list = byCat.get(def.category) ?? [];
      list.push(def);
      byCat.set(def.category, list);
    }
    return Array.from(byCat.entries())
      .map(([cat, defs]) => [cat, defs.sort((a, b) => a.displayName.localeCompare(b.displayName))] as const)
      .sort((a, b) => a[0].localeCompare(b[0]));
  }, [registry, query]);

  if (collapsed) return null;

  return (
    <aside className="flex w-64 flex-col border-r border-border bg-surface">
      <div className="border-b border-border p-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            className="w-full rounded border border-border bg-background py-1 pl-7 pr-2 text-xs outline-none"
            placeholder={t('palette.searchPlaceholder', 'Search nodes...')}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-1">
        {grouped.map(([category, defs]) => {
          const isOpen = open[category] ?? (!!query || true);
          return (
            <div key={category} className="mb-1">
              <button
                type="button"
                className="flex w-full items-center gap-1 rounded px-1.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground hover:bg-accent"
                onClick={() => setOpen((o) => ({ ...o, [category]: !isOpen }))}
              >
                {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                {category}
                <span className="ml-auto text-[10px] opacity-60">{defs.length}</span>
              </button>
              {isOpen && (
                <ul className="ml-1">
                  {defs.map((def) => (
                    <li key={def.type}>
                      <button
                        type="button"
                        draggable
                        onDragStart={(e) => {
                          e.dataTransfer.setData('application/leagent-node', def.type);
                          e.dataTransfer.effectAllowed = 'move';
                        }}
                        onClick={() => onAdd(def)}
                        title={def.description}
                        className={cn(
                          'w-full cursor-grab truncate rounded px-2 py-1 text-left text-xs hover:bg-accent active:cursor-grabbing',
                        )}
                      >
                        {def.displayName}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
