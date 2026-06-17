import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  BookOpenText,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  Loader2,
  Quote,
  Sigma,
  Sparkles,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Markdown } from '@/components/chat/markdown/Markdown';
import {
  fetchPdfCitations,
  fetchPdfFormulas,
  fetchPdfStructure,
  fetchPdfSummary,
} from './api/pdfReaderApi';
import type {
  PaperCitation,
  PaperFigure,
  PaperFormula,
  PaperSection,
  PdfStructureResponse,
} from './types';

type SidebarTab = 'outline' | 'figures' | 'formulas' | 'citations';

interface PaperSidebarProps {
  fileId: string;
  onJumpToPage: (page: number) => void;
  onAskAboutFigure: (figure: PaperFigure) => void;
  onShowSummary: (title: string, summary: string) => void;
  /** Jump to + highlight a figure/table region (falls back to page jump). */
  onFocusFigure?: (figure: PaperFigure) => void;
  /** Send a formula to the agent for professional analysis. */
  onAnalyzeFormula?: (formula: PaperFormula) => void;
  /** When provided, renders a close affordance in the header. */
  onClose?: () => void;
  /** Hide the internal title header (e.g. when hosted in a panel with its own). */
  hideHeader?: boolean;
  /** Hide the internal "Summarize paper" button (host provides its own). */
  hideSummarizeButton?: boolean;
}

export function PaperSidebar({
  fileId,
  onJumpToPage,
  onAskAboutFigure,
  onShowSummary,
  onFocusFigure,
  onAnalyzeFormula,
  onClose,
  hideHeader = false,
  hideSummarizeButton = false,
}: PaperSidebarProps) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<SidebarTab>('outline');
  const [structure, setStructure] = useState<PdfStructureResponse | null>(null);
  const [structureLoading, setStructureLoading] = useState(false);
  const [citations, setCitations] = useState<PaperCitation[] | null>(null);
  const [citationsLoading, setCitationsLoading] = useState(false);
  const [formulas, setFormulas] = useState<PaperFormula[] | null>(null);
  const [formulasLoading, setFormulasLoading] = useState(false);
  const [summarizing, setSummarizing] = useState<string | null>(null);

  const focusFigure = onFocusFigure ?? ((f: PaperFigure) => onJumpToPage(f.page));

  useEffect(() => {
    let cancelled = false;
    setStructureLoading(true);
    setStructure(null);
    setCitations(null);
    setFormulas(null);
    fetchPdfStructure(fileId)
      .then((res) => {
        if (!cancelled) setStructure(res);
      })
      .catch(() => {
        if (!cancelled) setStructure(null);
      })
      .finally(() => {
        if (!cancelled) setStructureLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [fileId]);

  const loadCitations = () => {
    if (citations || citationsLoading) return;
    setCitationsLoading(true);
    fetchPdfCitations(fileId)
      .then((res) => setCitations(res.citations))
      .catch(() => setCitations([]))
      .finally(() => setCitationsLoading(false));
  };

  const loadFormulas = () => {
    if (formulas || formulasLoading) return;
    setFormulasLoading(true);
    fetchPdfFormulas(fileId)
      .then((res) => setFormulas(res.formulas))
      .catch(() => setFormulas([]))
      .finally(() => setFormulasLoading(false));
  };

  const summarizeSection = async (section: PaperSection, endPage: number) => {
    setSummarizing(section.id);
    try {
      const res = await fetchPdfSummary(fileId, {
        startPage: section.page,
        endPage,
        sectionTitle: section.title,
      });
      onShowSummary(section.title, res.summary);
    } catch {
      onShowSummary(
        section.title,
        t('pdfReader.sidebar.summaryFailed', {
          defaultValue: 'Could not generate a summary for this section.',
        }),
      );
    } finally {
      setSummarizing(null);
    }
  };

  const summarizeWhole = async () => {
    setSummarizing('__whole__');
    try {
      const res = await fetchPdfSummary(fileId, {});
      onShowSummary(
        t('pdfReader.sidebar.wholePaper', { defaultValue: 'Whole paper' }),
        res.summary,
      );
    } catch {
      onShowSummary(
        t('pdfReader.sidebar.wholePaper', { defaultValue: 'Whole paper' }),
        t('pdfReader.sidebar.summaryFailed', {
          defaultValue: 'Could not generate a summary.',
        }),
      );
    } finally {
      setSummarizing(null);
    }
  };

  const sections = structure?.sections ?? [];
  const figures = structure?.figures ?? [];

  return (
    <div className="flex h-full w-full min-w-0 flex-col bg-transparent">
      {!hideHeader && (
        <div className="flex items-center gap-2 border-b border-border-subtle px-3 py-2">
          <BookOpenText className="h-4 w-4 text-primary-600" />
          <span className="flex-1 truncate text-sm font-semibold text-foreground">
            {t('pdfReader.sidebar.title', { defaultValue: 'Research Paper' })}
          </span>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded p-1 text-muted-foreground transition-colors hover:bg-surface-sunken hover:text-foreground"
              aria-label={t('common.close', { defaultValue: 'Close' })}
              title={t('common.close', { defaultValue: 'Close' })}
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      )}

      {!hideSummarizeButton && (
        <button
          type="button"
          onClick={summarizeWhole}
          disabled={summarizing === '__whole__'}
          className="mx-3 my-2 flex items-center justify-center gap-1.5 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition-colors hover:bg-primary-700 disabled:opacity-60"
        >
          {summarizing === '__whole__' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          {t('pdfReader.sidebar.summarizePaper', { defaultValue: 'Summarize paper' })}
        </button>
      )}

      <div className={cn('mx-3 mb-2 flex gap-1 rounded-lg bg-surface-sunken/60 p-0.5', !hideSummarizeButton ? '' : 'mt-2')}>
        <TabBtn
          active={tab === 'outline'}
          onClick={() => setTab('outline')}
          icon={<FileText className="h-3.5 w-3.5" />}
          label={t('pdfReader.sidebar.outline', { defaultValue: 'Outline' })}
        />
        <TabBtn
          active={tab === 'figures'}
          onClick={() => setTab('figures')}
          icon={<ImageIcon className="h-3.5 w-3.5" />}
          label={t('pdfReader.sidebar.figures', { defaultValue: 'Figures' })}
        />
        <TabBtn
          active={tab === 'formulas'}
          onClick={() => {
            setTab('formulas');
            loadFormulas();
          }}
          icon={<Sigma className="h-3.5 w-3.5" />}
          label={t('pdfReader.sidebar.formulas', { defaultValue: 'Formulas' })}
        />
        <TabBtn
          active={tab === 'citations'}
          onClick={() => {
            setTab('citations');
            loadCitations();
          }}
          icon={<Quote className="h-3.5 w-3.5" />}
          label={t('pdfReader.sidebar.citations', { defaultValue: 'Citations' })}
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {structureLoading && (
          <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('pdfReader.sidebar.analyzing', { defaultValue: 'Analyzing paper…' })}
          </div>
        )}

        {!structureLoading && tab === 'outline' && (
          <OutlineList
            sections={sections}
            summarizing={summarizing}
            onJump={onJumpToPage}
            onSummarize={summarizeSection}
            emptyLabel={t('pdfReader.sidebar.noOutline', {
              defaultValue: 'No outline detected.',
            })}
            summarizeLabel={t('pdfReader.sidebar.summarize', {
              defaultValue: 'Summarize',
            })}
          />
        )}

        {!structureLoading && tab === 'figures' && (
          <FigureList
            figures={figures}
            onFocus={focusFigure}
            onAsk={onAskAboutFigure}
            emptyLabel={t('pdfReader.sidebar.noFigures', {
              defaultValue: 'No figures or tables detected.',
            })}
            explainLabel={t('pdfReader.sidebar.explain', { defaultValue: 'Explain' })}
          />
        )}

        {tab === 'formulas' && (
          <FormulaList
            formulas={formulas}
            loading={formulasLoading}
            onJump={onJumpToPage}
            onAnalyze={onAnalyzeFormula}
            emptyLabel={t('pdfReader.sidebar.noFormulas', {
              defaultValue: 'No formulas detected.',
            })}
            analyzeLabel={t('pdfReader.sidebar.analyze', { defaultValue: 'Analyze' })}
            analyzingLabel={t('pdfReader.sidebar.analyzingFormulas', {
              defaultValue: 'Extracting formulas…',
            })}
            approxLabel={t('pdfReader.sidebar.formulasApprox', {
              defaultValue: 'AI service unavailable — showing a best-effort extraction.',
            })}
          />
        )}

        {tab === 'citations' && (
          <CitationList
            citations={citations}
            loading={citationsLoading}
            emptyLabel={t('pdfReader.sidebar.noCitations', {
              defaultValue: 'No references detected.',
            })}
          />
        )}
      </div>
    </div>
  );
}

function TabBtn({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex flex-1 items-center justify-center gap-1 whitespace-nowrap rounded-md px-1 py-1.5 text-[11px] font-medium transition-colors',
        active
          ? 'bg-surface text-primary-600 shadow-sm ring-1 ring-black/[0.04] dark:bg-surface/80 dark:text-primary-400 dark:ring-white/[0.06]'
          : 'text-muted-foreground hover:text-foreground',
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function OutlineList({
  sections,
  summarizing,
  onJump,
  onSummarize,
  emptyLabel,
  summarizeLabel,
}: {
  sections: PaperSection[];
  summarizing: string | null;
  onJump: (page: number) => void;
  onSummarize: (section: PaperSection, endPage: number) => void;
  emptyLabel: string;
  summarizeLabel: string;
}) {
  if (sections.length === 0) {
    return <Empty label={emptyLabel} />;
  }
  return (
    <ul className="space-y-0.5">
      {sections.map((s, i) => {
        const endPage = sections[i + 1]?.page ?? s.page + 2;
        return (
          <li key={s.id} className="group flex items-center gap-1">
            <button
              type="button"
              onClick={() => onJump(s.page)}
              className="min-w-0 flex-1 truncate rounded px-2 py-1.5 text-left text-xs text-foreground hover:bg-surface-sunken"
              style={{ paddingLeft: `${0.5 + (s.level - 1) * 0.75}rem` }}
              title={s.title}
            >
              {s.title}
              <span className="ml-1 rounded bg-surface-sunken px-1 py-px text-[10px] tabular-nums text-muted-foreground">
                p.{s.page}
              </span>
            </button>
            <button
              type="button"
              onClick={() => onSummarize(s, endPage)}
              disabled={summarizing === s.id}
              title={summarizeLabel}
              className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-surface-sunken hover:text-primary-600 group-hover:opacity-100"
            >
              {summarizing === s.id ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Sparkles className="h-3 w-3" />
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function FigureList({
  figures,
  onFocus,
  onAsk,
  emptyLabel,
  explainLabel,
}: {
  figures: PaperFigure[];
  onFocus: (figure: PaperFigure) => void;
  onAsk: (figure: PaperFigure) => void;
  emptyLabel: string;
  explainLabel: string;
}) {
  if (figures.length === 0) {
    return <Empty label={emptyLabel} />;
  }
  return (
    <ul className="space-y-1">
      {figures.map((f) => (
        <li
          key={f.id}
          className="flex items-center gap-1 rounded px-2 py-1.5 hover:bg-surface-sunken"
        >
          <button
            type="button"
            onClick={() => onFocus(f)}
            className="min-w-0 flex-1 truncate text-left text-xs text-foreground"
            title={f.label}
          >
            {f.label}
            <span className="ml-1 rounded bg-surface-sunken px-1 py-px text-[10px] tabular-nums text-muted-foreground">
              p.{f.page}
            </span>
          </button>
          <button
            type="button"
            onClick={() => onAsk(f)}
            className="flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md bg-primary-500/10 px-1.5 py-0.5 text-[10px] font-medium text-primary-600 transition-colors hover:bg-primary-500/20 dark:text-primary-400"
          >
            <Sparkles className="h-3 w-3" />
            {explainLabel}
          </button>
        </li>
      ))}
    </ul>
  );
}

function CitationList({
  citations,
  loading,
  emptyLabel,
}: {
  citations: PaperCitation[] | null;
  loading: boolean;
  emptyLabel: string;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
      </div>
    );
  }
  if (!citations || citations.length === 0) {
    return <Empty label={emptyLabel} />;
  }
  return (
    <ul className="space-y-2">
      {citations.map((c) => (
        <li key={c.id} className="rounded-lg border border-border-subtle/70 bg-surface-sunken/30 p-2">
          <p className="text-[11px] leading-snug text-foreground">
            {c.marker && (
              <span className="mr-1 font-semibold text-primary-600">{c.marker}</span>
            )}
            {c.text}
          </p>
          {(c.doi || c.url) && (
            <a
              href={c.url ?? `https://doi.org/${c.doi}`}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-[10px] font-medium text-primary-600 hover:underline"
            >
              <ExternalLink className="h-3 w-3" />
              {c.doi ?? c.url}
            </a>
          )}
        </li>
      ))}
    </ul>
  );
}

function FormulaList({
  formulas,
  loading,
  onJump,
  onAnalyze,
  emptyLabel,
  analyzeLabel,
  analyzingLabel,
  approxLabel,
}: {
  formulas: PaperFormula[] | null;
  loading: boolean;
  onJump: (page: number) => void;
  onAnalyze?: (formula: PaperFormula) => void;
  emptyLabel: string;
  analyzeLabel: string;
  analyzingLabel: string;
  approxLabel: string;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {analyzingLabel}
      </div>
    );
  }
  if (!formulas || formulas.length === 0) {
    return <Empty label={emptyLabel} />;
  }
  const isApprox = formulas.some((f) => f.approx);
  return (
    <div className="space-y-2">
      {isApprox && (
        <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 text-[11px] leading-snug text-amber-700 dark:text-amber-400">
          {approxLabel}
        </p>
      )}
      <ul className="space-y-2">
        {formulas.map((f) => (
          <li
            key={f.id}
            className="rounded-lg border border-border-subtle/70 bg-surface-sunken/30 p-2"
          >
            <div className="flex items-center gap-2">
              {f.label && (
                <span className="shrink-0 rounded bg-surface-sunken px-1 py-px text-[10px] font-semibold tabular-nums text-primary-600 dark:text-primary-400">
                  {f.label}
                </span>
              )}
              <div className="ml-auto flex shrink-0 items-center gap-1">
                {f.page ? (
                  <button
                    type="button"
                    onClick={() => onJump(f.page as number)}
                    className="rounded bg-surface-sunken px-1 py-px text-[10px] tabular-nums text-muted-foreground transition-colors hover:text-foreground"
                    title={`p.${f.page}`}
                  >
                    p.{f.page}
                  </button>
                ) : null}
                {onAnalyze && (
                  <button
                    type="button"
                    onClick={() => onAnalyze(f)}
                    className="flex items-center gap-1 whitespace-nowrap rounded-md bg-primary-500/10 px-1.5 py-0.5 text-[10px] font-medium text-primary-600 transition-colors hover:bg-primary-500/20 dark:text-primary-400"
                  >
                    <Sparkles className="h-3 w-3" />
                    {analyzeLabel}
                  </button>
                )}
              </div>
            </div>
            {f.approx ? (
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-surface-sunken/60 p-1.5 font-mono text-[12px] leading-snug text-foreground">
                {f.latex}
              </pre>
            ) : (
              <div className="mt-1 overflow-x-auto text-[13px] leading-snug">
                <Markdown content={`$$\n${f.latex}\n$$`} />
              </div>
            )}
            {f.description && (
              <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
                {f.description}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return <p className="px-2 py-6 text-center text-xs text-muted-foreground">{label}</p>;
}
