import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Fuse from 'fuse.js';

import { cn } from '@/lib/utils';

import type { NodeDefinition, ObjectInfo } from '../graph/objectInfo';
import { typesCompatible } from '../graph/socketTypes';

export interface PaletteTypeFilter {
  /** Wire type of the dangling link end. */
  type: string;
  /** 'out': dragging from an output, so candidates need a compatible input. */
  direction: 'out' | 'in';
}

interface NodeSearchPaletteProps {
  registry: ObjectInfo;
  onSelect: (def: NodeDefinition) => void;
  onClose: () => void;
  /** Restrict results to nodes connectable to a dangling link (link-release). */
  typeFilter?: PaletteTypeFilter | null;
}

function connectable(def: NodeDefinition, filter: PaletteTypeFilter): boolean {
  if (filter.direction === 'out') {
    return def.inputs.some((slot) => typesCompatible(filter.type, slot.type));
  }
  return def.outputs.some((slot) => typesCompatible(slot.type, filter.type));
}

/**
 * Canvas-first node search (litegraph-style). Opened by double-clicking the
 * canvas, a hotkey, or releasing a link on empty canvas (which filters to
 * type-compatible nodes and auto-connects on pick). Fuzzy matching via Fuse.
 */
export function NodeSearchPalette({
  registry,
  onSelect,
  onClose,
  typeFilter,
}: NodeSearchPaletteProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const candidates = useMemo(() => {
    let all = Object.values(registry.definitions).filter((d) => !d.deprecated);
    if (typeFilter) all = all.filter((d) => connectable(d, typeFilter));
    return all;
  }, [registry, typeFilter]);

  const fuse = useMemo(
    () =>
      new Fuse(candidates, {
        keys: [
          { name: 'displayName', weight: 0.5 },
          { name: 'type', weight: 0.3 },
          { name: 'category', weight: 0.15 },
          { name: 'description', weight: 0.05 },
        ],
        threshold: 0.35,
        ignoreLocation: true,
      }),
    [candidates],
  );

  const results = useMemo(() => {
    const q = query.trim();
    if (!q) {
      return [...candidates]
        .sort((a, b) => a.displayName.localeCompare(b.displayName))
        .slice(0, 50);
    }
    return fuse.search(q, { limit: 50 }).map((r) => r.item);
  }, [candidates, fuse, query]);

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
        className="w-[420px] max-w-[90%] overflow-hidden rounded-lg border border-border bg-surface-elevated shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {typeFilter && (
          <div className="flex items-center gap-1.5 border-b border-border bg-surface-sunken px-3 py-1.5 text-[11px] text-muted-foreground">
            {t('palette.typeFilter', 'Compatible with')}
            <code className="rounded bg-surface-sunken px-1 font-mono text-[10px]">
              {typeFilter.type}
            </code>
          </div>
        )}
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
                  'flex w-full flex-col items-start gap-0.5 px-3 py-1.5 text-left text-sm hover:bg-surface-sunken',
                  i === active && 'bg-surface-sunken',
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
