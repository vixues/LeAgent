import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';

import type { NodeDefinition, ObjectInfo } from '../graph/objectInfo';

interface NodeSearchPaletteProps {
  registry: ObjectInfo;
  onSelect: (def: NodeDefinition) => void;
  onClose: () => void;
}

/**
 * Canvas-first node search (litegraph-style). Opened by double-clicking the
 * canvas or a hotkey; type to filter the full `/object_info` catalog and
 * press Enter / click to drop the node at the cursor.
 */
export function NodeSearchPalette({ registry, onSelect, onClose }: NodeSearchPaletteProps) {
  const { t } = useTranslation('workflows');
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const results = useMemo(() => {
    const all = Object.values(registry.definitions).filter((d) => !d.deprecated);
    const q = query.trim().toLowerCase();
    const filtered = q
      ? all.filter(
          (d) =>
            d.displayName.toLowerCase().includes(q) ||
            d.type.toLowerCase().includes(q) ||
            d.category.toLowerCase().includes(q),
        )
      : all;
    return filtered
      .sort((a, b) => a.displayName.localeCompare(b.displayName))
      .slice(0, 50);
  }, [registry, query]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  const choose = (def: NodeDefinition | undefined) => {
    if (def) onSelect(def);
  };

  return (
    <div
      className="absolute inset-0 z-50 flex items-start justify-center bg-black/30 pt-24"
      onClick={onClose}
    >
      <div
        className="w-[420px] max-w-[90%] overflow-hidden rounded-lg border border-border bg-popover shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          className="w-full border-b border-border bg-transparent px-3 py-2 text-sm outline-none"
          placeholder={t('palette.searchPlaceholder', 'Search nodes...')}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') onClose();
            else if (e.key === 'ArrowDown') {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, results.length - 1));
            } else if (e.key === 'ArrowUp') {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === 'Enter') {
              e.preventDefault();
              choose(results[active]);
            }
          }}
        />
        <ul className="max-h-80 overflow-auto py-1">
          {results.length === 0 && (
            <li className="px-3 py-2 text-xs text-muted-foreground">
              {t('palette.noResults', 'No matching nodes')}
            </li>
          )}
          {results.map((def, i) => (
            <li key={def.type}>
              <button
                type="button"
                className={cn(
                  'flex w-full flex-col items-start gap-0.5 px-3 py-1.5 text-left text-sm hover:bg-accent',
                  i === active && 'bg-accent',
                )}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(def)}
              >
                <span className="font-medium">{def.displayName}</span>
                <span className="text-[10px] text-muted-foreground">{def.category}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
