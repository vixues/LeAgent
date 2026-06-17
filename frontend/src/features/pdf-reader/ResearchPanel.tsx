import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  BookOpenText,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  Loader2,
  ShieldAlert,
  Sparkles,
  Trophy,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { PaperSidebar } from './PaperSidebar';
import { fetchPdfSummary } from './api/pdfReaderApi';
import { usePdfResearchStore } from './store/pdfResearchStore';
import {
  appendPrompt,
  ensurePaperReferenced,
  focusComposer,
  insertQuote,
} from './readerComposerBridge';
import type { PaperFigure, PaperFormula } from './types';

/**
 * Top-of-chat Research Paper panel. Styled after the task/execution panel
 * (`ChatExecutionPanel`): a collapsible glass card pinned above the conversation
 * that hosts the structured `PaperSidebar`. Only mounts while research mode is
 * active (driven by `usePdfResearchStore`).
 */
export function ResearchPanel() {
  const { t } = useTranslation();
  const target = usePdfResearchStore((s) => s.target);
  const requestPage = usePdfResearchStore((s) => s.requestPage);
  const focusRegion = usePdfResearchStore((s) => s.focusRegion);
  const stop = usePdfResearchStore((s) => s.stop);
  const [expanded, setExpanded] = useState(true);
  const [summarizing, setSummarizing] = useState(false);
  const [summary, setSummary] = useState<{ title: string; body: string } | null>(null);

  if (!target) return null;

  const onAskAboutFigure = (figure: PaperFigure) => {
    requestPage(figure.page);
    ensurePaperReferenced(target);
    insertQuote(
      t('pdfReader.figure.askPrompt', {
        defaultValue: 'Explain {{label}} (page {{page}}) in this paper.',
        label: figure.label,
        page: figure.page,
      }),
    );
  };

  const summarizeWhole = async () => {
    if (summarizing) return;
    const title = t('pdfReader.sidebar.wholePaper', { defaultValue: 'Whole paper' });
    setExpanded(true);
    setSummarizing(true);
    try {
      const res = await fetchPdfSummary(target.fileId, {});
      setSummary({ title, body: res.summary });
    } catch {
      setSummary({
        title,
        body: t('pdfReader.sidebar.summaryFailed', {
          defaultValue: 'Could not generate a summary.',
        }),
      });
    } finally {
      setSummarizing(false);
    }
  };

  const askPaper = (prompt: string) => {
    ensurePaperReferenced(target);
    appendPrompt(prompt);
    focusComposer();
  };

  const onFocusFigure = (figure: PaperFigure) => {
    if (figure.bbox && figure.bbox.length === 4) {
      const [x0 = 0, y0 = 0, x1 = 0, y1 = 0] = figure.bbox;
      focusRegion({
        page: figure.page,
        x: x0,
        y: y0,
        width: x1 - x0,
        height: y1 - y0,
      });
    } else {
      requestPage(figure.page);
    }
  };

  const onAnalyzeFormula = (formula: PaperFormula) => {
    ensurePaperReferenced(target);
    const pageRef = formula.page ? ` (p.${formula.page})` : '';
    appendPrompt(
      t('pdfReader.sidebar.analyzeFormulaPrompt', {
        defaultValue:
          'Analyze this formula from the paper{{page}} in depth: define every symbol, explain what it computes and why, and note assumptions or limitations.',
        page: pageRef,
      }) + `\n\n$$\n${formula.latex}\n$$`,
    );
    focusComposer();
  };

  const quickActions = [
    {
      key: 'contributions',
      icon: <Trophy className="h-3.5 w-3.5" />,
      label: t('pdfReader.dock.prompts.contributions', { defaultValue: 'Key contributions?' }),
    },
    {
      key: 'methods',
      icon: <FlaskConical className="h-3.5 w-3.5" />,
      label: t('pdfReader.dock.prompts.methods', { defaultValue: 'Explain the methods' }),
    },
    {
      key: 'limitations',
      icon: <ShieldAlert className="h-3.5 w-3.5" />,
      label: t('pdfReader.dock.prompts.limitations', { defaultValue: 'Limitations & future work?' }),
    },
  ];

  return (
    <div className="chat-todo-panel-row">
      <div className="chat-composer-inner min-w-0">
        <div
          className={cn(
            'rounded-xl border border-border-subtle/80 bg-surface/65 shadow-md ring-1 ring-black/[0.04] backdrop-blur-md backdrop-saturate-150',
            'dark:bg-surface/55 dark:ring-white/[0.06]',
          )}
        >
          <div className="flex items-center gap-1 border-b border-border-subtle/80 px-2 py-1.5">
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="flex min-w-0 items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-muted/40"
              aria-expanded={expanded}
            >
              {expanded ? (
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground-tertiary" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground-tertiary" />
              )}
              <BookOpenText className="h-3.5 w-3.5 shrink-0 text-primary-600" />
              <span className="truncate text-xs font-medium text-foreground/90">
                {t('pdfReader.sidebar.title', { defaultValue: 'Research Paper' })}
              </span>
            </button>

            <span className="hidden min-w-0 flex-1 truncate text-[11px] text-muted-foreground-tertiary lg:inline">
              · {target.fileName}
            </span>

            <div className="ml-auto flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={() => void summarizeWhole()}
                disabled={summarizing}
                className="flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md bg-primary-600 px-2.5 py-1 text-xs font-medium text-white shadow-sm transition-colors hover:bg-primary-700 disabled:opacity-60"
                title={t('pdfReader.sidebar.summarizePaper', { defaultValue: 'Summarize paper' })}
              >
                {summarizing ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Sparkles className="h-3.5 w-3.5" />
                )}
                {t('pdfReader.sidebar.summarizePaper', { defaultValue: 'Summarize paper' })}
              </button>

              {quickActions.map((a) => (
                <button
                  key={a.key}
                  type="button"
                  onClick={() => askPaper(a.label)}
                  className="hidden shrink-0 items-center gap-1 whitespace-nowrap rounded-md bg-surface-sunken/70 px-2 py-1 text-xs font-medium text-foreground transition-colors hover:bg-surface-sunken md:flex"
                  title={a.label}
                >
                  <span className="text-primary-600 dark:text-primary-400">{a.icon}</span>
                  <span className="hidden xl:inline">{a.label}</span>
                </button>
              ))}

              <button
                type="button"
                onClick={stop}
                className="shrink-0 rounded-md p-1.5 text-muted-foreground-tertiary hover:bg-muted/40 hover:text-foreground"
                title={t('common.close', { defaultValue: 'Close' })}
                aria-label={t('common.close', { defaultValue: 'Close' })}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {expanded ? (
            <div className="relative flex h-[clamp(220px,38vh,460px)] min-h-0 flex-col">
              <PaperSidebar
                key={target.fileId}
                fileId={target.fileId}
                hideHeader
                hideSummarizeButton
                onJumpToPage={requestPage}
                onAskAboutFigure={onAskAboutFigure}
                onFocusFigure={onFocusFigure}
                onAnalyzeFormula={onAnalyzeFormula}
                onShowSummary={(title, body) => setSummary({ title, body })}
              />

              {summary && (
                <div
                  className="absolute inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
                  onClick={() => setSummary(null)}
                >
                  <div
                    className="max-h-[90%] w-full overflow-y-auto rounded-xl border border-border bg-surface p-5 shadow-2xl"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <h3 className="text-sm font-semibold text-foreground">{summary.title}</h3>
                      <button
                        type="button"
                        onClick={() => setSummary(null)}
                        className="rounded p-1 text-muted-foreground hover:bg-surface-sunken"
                        aria-label={t('common.close', { defaultValue: 'Close' })}
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                      {summary.body}
                    </p>
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
