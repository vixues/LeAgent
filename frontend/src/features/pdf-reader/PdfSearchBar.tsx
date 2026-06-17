import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronUp, Loader2, Search, X } from 'lucide-react';
import type { PdfDocument } from './pdfjs';

export interface SearchMatch {
  page: number;
  snippet: string;
}

interface PdfSearchBarProps {
  doc: PdfDocument;
  onJump: (page: number) => void;
  onClose: () => void;
}

/** Lightweight whole-document text search (scans `getTextContent` per page). */
export function PdfSearchBar({ doc, onJump, onClose }: PdfSearchBarProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [matches, setMatches] = useState<SearchMatch[]>([]);
  const [active, setActive] = useState(0);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);

  const runSearch = async () => {
    const q = query.trim().toLowerCase();
    if (!q) return;
    setSearching(true);
    setSearched(false);
    const found: SearchMatch[] = [];
    try {
      for (let p = 1; p <= doc.numPages; p += 1) {
        const page = await doc.getPage(p);
        const content = await page.getTextContent();
        const text = content.items
          .map((it) => ('str' in it ? it.str : ''))
          .join(' ');
        const lower = text.toLowerCase();
        let idx = lower.indexOf(q);
        while (idx !== -1) {
          const start = Math.max(0, idx - 30);
          const end = Math.min(text.length, idx + q.length + 30);
          found.push({
            page: p,
            snippet: `…${text.slice(start, end).trim()}…`,
          });
          idx = lower.indexOf(q, idx + q.length);
          if (found.length > 200) break;
        }
        if (found.length > 200) break;
      }
    } finally {
      setMatches(found);
      setActive(0);
      setSearching(false);
      setSearched(true);
      if (found[0]) onJump(found[0].page);
    }
  };

  const goto = (delta: number) => {
    if (matches.length === 0) return;
    const next = (active + delta + matches.length) % matches.length;
    setActive(next);
    const match = matches[next];
    if (match) onJump(match.page);
  };

  return (
    <div className="absolute right-3 top-2 z-30 w-80 rounded-lg border border-border bg-surface p-2 shadow-lg">
      <div className="flex items-center gap-1">
        <Search className="h-4 w-4 text-muted-foreground" />
        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void runSearch();
            if (e.key === 'Escape') onClose();
          }}
          placeholder={t('pdfReader.search.placeholder', {
            defaultValue: 'Search in document…',
          })}
          className="h-7 flex-1 bg-transparent text-sm text-foreground outline-none"
        />
        {searching && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
        {matches.length > 0 && (
          <span className="text-[11px] tabular-nums text-muted-foreground">
            {active + 1}/{matches.length}
          </span>
        )}
        <button
          type="button"
          onClick={() => goto(-1)}
          disabled={matches.length === 0}
          className="rounded p-1 text-muted-foreground hover:bg-surface-sunken disabled:opacity-40"
        >
          <ChevronUp className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={() => goto(1)}
          disabled={matches.length === 0}
          className="rounded p-1 text-muted-foreground hover:bg-surface-sunken disabled:opacity-40"
        >
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-muted-foreground hover:bg-surface-sunken"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      {searched && matches.length === 0 && (
        <p className="px-1 pt-1.5 text-[11px] text-muted-foreground">
          {t('pdfReader.search.noResults', { defaultValue: 'No results found.' })}
        </p>
      )}
      {matches.length > 0 && (
        <div className="mt-1.5 max-h-48 overflow-y-auto">
          {matches.map((m, i) => (
            <button
              key={`${m.page}-${i}`}
              type="button"
              onClick={() => {
                setActive(i);
                onJump(m.page);
              }}
              className={`block w-full rounded px-1.5 py-1 text-left text-[11px] leading-snug hover:bg-surface-sunken ${
                i === active ? 'bg-surface-sunken' : ''
              }`}
            >
              <span className="font-medium text-primary-600 dark:text-primary-400">
                p.{m.page}
              </span>{' '}
              <span className="text-muted-foreground">{m.snippet}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
