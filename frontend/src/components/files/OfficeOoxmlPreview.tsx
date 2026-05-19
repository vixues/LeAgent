import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { getAccessToken } from '@/api/client';
import { cn } from '@/lib/utils';
import type { OfficePreviewRoute } from '@/lib/mimeForPreview';

export type OfficeOoxmlLayout = 'default' | 'fill';

export type OfficeOoxmlPreviewRoute = Extract<
  OfficePreviewRoute,
  'docx' | 'xlsx' | 'pptx'
>;

const OFFICE_PREVIEW_MAX_BYTES = 20 * 1024 * 1024;
const MAX_XLSX_ROWS = 500;
const MAX_XLSX_COLS = 64;

const SCROLL_MAX_DEFAULT = 'max-h-[min(65vh,28rem)]';

function formatXlsxCell(value: unknown): string {
  if (value == null) return '';
  if (value instanceof Date) return value.toLocaleString();
  if (typeof value === 'boolean') return value ? 'TRUE' : 'FALSE';
  return String(value);
}

interface OfficeOoxmlPreviewProps {
  previewUrl: string;
  route: OfficeOoxmlPreviewRoute;
  fileName: string;
  layout?: OfficeOoxmlLayout;
  className?: string;
}

type FetchPhase = 'idle' | 'loading' | 'ready' | 'error' | 'tooLarge';

export function OfficeOoxmlPreview({
  previewUrl,
  route,
  fileName,
  layout = 'default',
  className,
}: OfficeOoxmlPreviewProps) {
  const { t } = useTranslation();
  const fill = layout === 'fill';

  const [phase, setPhase] = useState<FetchPhase>('idle');
  const [buffer, setBuffer] = useState<ArrayBuffer | null>(null);
  const [parseFailed, setParseFailed] = useState(false);

  const handleParseError = useCallback(() => {
    setParseFailed(true);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setPhase('loading');
    setBuffer(null);
    setParseFailed(false);

    const token = getAccessToken();
    fetch(previewUrl, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      credentials: 'include',
    })
      .then(async (res) => {
        if (!res.ok) throw new Error('Preview request failed');
        const len = res.headers.get('Content-Length');
        if (len && Number(len) > OFFICE_PREVIEW_MAX_BYTES) {
          setPhase('tooLarge');
          return;
        }
        const buf = await res.arrayBuffer();
        if (cancelled) return;
        if (buf.byteLength > OFFICE_PREVIEW_MAX_BYTES) {
          setPhase('tooLarge');
          return;
        }
        setBuffer(buf);
        setPhase('ready');
      })
      .catch(() => {
        if (!cancelled) setPhase('error');
      });

    return () => {
      cancelled = true;
    };
  }, [previewUrl]);

  const scrollWrapClass = fill
    ? 'flex min-h-0 w-full flex-1 flex-col overflow-hidden'
    : cn(SCROLL_MAX_DEFAULT, 'min-h-0 overflow-y-auto overscroll-y-contain');

  let body: ReactNode;
  if (phase === 'loading' || phase === 'idle') {
    body = (
      <div
        className={cn(
          'rounded-lg border border-border bg-surface-sunken p-5 text-center',
          fill && 'flex min-h-0 flex-1 flex-col justify-center',
        )}
      >
        <p className="text-sm text-muted-foreground">
          {t('common.filePreview.loading')}
        </p>
      </div>
    );
  } else if (phase === 'error') {
    body = (
      <div
        className={cn(
          'rounded-lg border border-border bg-surface-sunken p-5 text-center',
          fill && 'flex min-h-0 flex-1 flex-col justify-center',
        )}
      >
        <p className="text-sm text-muted-foreground">
          {t('common.filePreview.error')}
        </p>
      </div>
    );
  } else if (phase === 'tooLarge') {
    body = (
      <div
        className={cn(
          'rounded-lg border border-border bg-surface-sunken p-5 text-center',
          fill && 'flex min-h-0 flex-1 flex-col justify-center',
        )}
      >
        <p className="text-sm text-muted-foreground">
          {t('common.filePreview.tooLarge')}
        </p>
      </div>
    );
  } else if (phase === 'ready' && buffer) {
    if (route === 'docx') {
      body = (
        <DocxPreviewPane
          buffer={buffer}
          scrollWrapClass={scrollWrapClass}
          fill={fill}
          onError={handleParseError}
        />
      );
    } else if (route === 'xlsx') {
      body = (
        <XlsxPreviewPane
          buffer={buffer}
          scrollWrapClass={scrollWrapClass}
          fill={fill}
          fileName={fileName}
          onError={handleParseError}
        />
      );
    } else {
      body = (
        <PptxPreviewPane
          buffer={buffer}
          scrollWrapClass={scrollWrapClass}
          fill={fill}
          fileName={fileName}
          onError={handleParseError}
        />
      );
    }
  } else {
    body = null;
  }

  const showParseError = parseFailed && phase === 'ready' && buffer;

  return (
    <div
      className={cn(
        'flex min-h-0 w-full flex-col',
        fill && 'min-h-0 flex-1',
        className,
      )}
    >
      {showParseError ? (
        <div
          className={cn(
            'rounded-lg border border-border bg-surface-sunken p-5 text-center',
            fill && 'flex min-h-0 flex-1 flex-col justify-center',
          )}
        >
          <p className="text-sm text-muted-foreground">
            {t('common.filePreview.parseError')}
          </p>
        </div>
      ) : (
        body
      )}
    </div>
  );
}

function DocxPreviewPane({
  buffer,
  scrollWrapClass,
  fill,
  onError,
}: {
  buffer: ArrayBuffer;
  scrollWrapClass: string;
  fill: boolean;
  onError: () => void;
}) {
  const { t } = useTranslation();
  const [html, setHtml] = useState<string | null>(null);
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  useEffect(() => {
    let cancelled = false;
    setHtml(null);
    void (async () => {
      try {
        const mammoth = await import('mammoth');
        const DOMPurify = (await import('dompurify')).default;
        const result = await mammoth.convertToHtml({ arrayBuffer: buffer });
        if (cancelled) return;
        setHtml(DOMPurify.sanitize(result.value));
      } catch {
        if (!cancelled) onErrorRef.current();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [buffer]);

  if (!html) {
    return (
      <div
        className={cn(
          'rounded-lg border border-border bg-surface-sunken p-5 text-center',
          fill && 'flex min-h-0 flex-1 flex-col justify-center',
        )}
      >
        <p className="text-sm text-muted-foreground">
          {t('common.filePreview.loading')}
        </p>
      </div>
    );
  }

  if (fill) {
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-border bg-surface-sunken">
        <div
          className="prose prose-sm dark:prose-invert max-w-none min-h-0 flex-1 overflow-y-auto overscroll-y-contain px-3 py-3 text-foreground [&_img]:max-w-full [&_table]:text-xs"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </div>
    );
  }

  return (
    <div
      className={cn(
        'rounded-lg border border-border bg-surface-sunken p-3',
        scrollWrapClass,
      )}
    >
      <div
        className="prose prose-sm dark:prose-invert max-w-none text-foreground px-1 [&_img]:max-w-full [&_table]:text-xs"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
}

function XlsxPreviewPane({
  buffer,
  scrollWrapClass,
  fill,
  fileName,
  onError,
}: {
  buffer: ArrayBuffer;
  scrollWrapClass: string;
  fill: boolean;
  fileName: string;
  onError: () => void;
}) {
  const { t } = useTranslation();
  const [sheets, setSheets] = useState<
    { sheet: string; rows: unknown[][] }[] | null
  >(null);
  const [sheetIndex, setSheetIndex] = useState(0);
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  useEffect(() => {
    let cancelled = false;
    setSheets(null);
    setSheetIndex(0);
    void (async () => {
      try {
        const mod = await import('read-excel-file/browser');
        const readXlsxFile = mod.default;
        const blob = new Blob([buffer], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        });
        const parsed = await readXlsxFile(blob);
        if (cancelled) return;
        const normalized = parsed.map((s) => ({
          sheet: s.sheet,
          rows: s.data as unknown[][],
        }));
        setSheets(normalized);
      } catch {
        if (!cancelled) onErrorRef.current();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [buffer]);

  const active = sheets !== null ? sheets[sheetIndex] : undefined;

  const tableModel = useMemo(() => {
    if (!active?.rows?.length) return null;
    const src = active.rows;
    const sliceRows = src.slice(0, MAX_XLSX_ROWS);
    const truncatedRows = src.length > MAX_XLSX_ROWS;
    let truncatedCols = false;
    for (const row of src) {
      if (row.length > MAX_XLSX_COLS) {
        truncatedCols = true;
        break;
      }
    }
    let width = 1;
    for (const row of sliceRows) {
      width = Math.max(width, Math.min(row.length, MAX_XLSX_COLS));
    }
    width = Math.min(width, MAX_XLSX_COLS);
    const padded = sliceRows.map((row) => {
      const next: unknown[] = [];
      for (let c = 0; c < width; c++) {
        next.push(c < row.length ? row[c] : '');
      }
      return next;
    });
    return {
      rows: padded,
      truncatedRows,
      truncatedCols,
      width,
    };
  }, [active]);

  if (sheets === null) {
    return (
      <div
        className={cn(
          'rounded-lg border border-border bg-surface-sunken p-5 text-center',
          fill && 'flex min-h-0 flex-1 flex-col justify-center',
        )}
      >
        <p className="text-sm text-muted-foreground">
          {t('common.filePreview.loading')}
        </p>
      </div>
    );
  }

  if (sheets.length === 0) {
    return (
      <div
        className={cn(
          'rounded-lg border border-border bg-surface-sunken p-5 text-center',
          fill && 'flex min-h-0 flex-1 flex-col justify-center',
        )}
      >
        <p className="text-sm text-muted-foreground">
          {t('common.filePreview.xlsxEmpty')}
        </p>
      </div>
    );
  }

  if (!active?.rows?.length || !tableModel) {
    return (
      <div
        className={cn(
          'rounded-lg border border-border bg-surface-sunken p-5 text-center',
          fill && 'flex min-h-0 flex-1 flex-col justify-center',
        )}
      >
        <p className="text-sm text-muted-foreground">
          {t('common.filePreview.xlsxEmpty')}
        </p>
      </div>
    );
  }

  const showTrunc = tableModel.truncatedRows || tableModel.truncatedCols;

  return (
    <div
      className={cn(
        'flex min-h-0 flex-col gap-2 rounded-lg border border-border bg-surface-sunken p-3',
        scrollWrapClass,
      )}
    >
      {sheets.length > 1 ? (
        <label className="flex flex-shrink-0 items-center gap-2 text-xs text-muted-foreground">
          <span className="whitespace-nowrap">{t('common.filePreview.worksheet')}</span>
          <select
            className="max-w-full flex-1 rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs text-foreground"
            value={sheetIndex}
            onChange={(e) => setSheetIndex(Number(e.target.value))}
            aria-label={fileName}
          >
            {sheets.map((s, i) => (
              <option key={`${s.sheet}-${i}`} value={i}>
                {s.sheet || `Sheet ${i + 1}`}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {showTrunc ? (
        <p className="flex-shrink-0 text-[11px] text-muted-foreground leading-snug">
          {t('common.filePreview.tableTruncated', {
            maxRows: MAX_XLSX_ROWS,
            maxCols: MAX_XLSX_COLS,
          })}
        </p>
      ) : null}
      <div className="min-h-0 flex-1 overflow-auto rounded-md border border-border-subtle">
        <table className="w-max min-w-full border-collapse text-left text-[11px] text-foreground">
          <tbody>
            {tableModel.rows.map((dataRow, rowIdx) => (
              <tr
                key={rowIdx}
                className="even:bg-surface-sunken/35 border-b border-border-subtle/60 last:border-b-0"
              >
                {Array.from({ length: tableModel.width }, (_, colIdx) => (
                  <td
                    key={colIdx}
                    className="max-w-[min(18rem,45vw)] px-2 py-1.5 align-top leading-snug"
                  >
                    <span className="block break-words whitespace-normal text-foreground">
                      {formatXlsxCell(dataRow[colIdx]) || '\u00a0'}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PptxPreviewPane({
  buffer,
  scrollWrapClass,
  fill,
  fileName,
  onError,
}: {
  buffer: ArrayBuffer;
  scrollWrapClass: string;
  fill: boolean;
  fileName: string;
  onError: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<{ destroy: () => void } | null>(null);
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let cancelled = false;
    void (async () => {
      try {
        const { PPTXViewer } = await import('pptx-viewer');
        if (cancelled || !containerRef.current) return;
        const viewer = new PPTXViewer(containerRef.current, {
          showControls: true,
          keyboardNavigation: true,
        });
        viewerRef.current = viewer;
        await viewer.load(buffer);
      } catch {
        if (!cancelled) onErrorRef.current();
      }
    })();

    return () => {
      cancelled = true;
      viewerRef.current?.destroy();
      viewerRef.current = null;
    };
  }, [buffer]);

  return (
    <div
      className={cn(
        'flex min-h-0 w-full flex-col gap-2',
        scrollWrapClass,
      )}
    >
      <div
        ref={containerRef}
        className={cn(
          'w-full min-h-[min(50vh,24rem)] rounded-lg border border-border bg-surface-sunken',
          fill ? 'min-h-0 flex-1' : 'max-h-[min(70vh,28rem)]',
        )}
        aria-label={fileName}
      />
    </div>
  );
}
