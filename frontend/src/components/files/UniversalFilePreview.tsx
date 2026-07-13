import {
  lazy,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Download, ExternalLink, FileText, GraduationCap } from 'lucide-react';
import { Button } from '@/components/ui';
import { getAccessToken } from '@/api/client';
import { cn } from '@/lib/utils';

const PdfReader = lazy(() =>
  import('@/features/pdf-reader/PdfReader').then((m) => ({ default: m.PdfReader })),
);
import {
  resolveEffectiveMime,
  isTextLikeMime,
  isJsonPreviewMime,
  isMarkdownPreviewMime,
  isCsvPreviewMime,
  looksLikeBinaryString,
  isOfficeDocumentMime,
  hasOfficePreviewExtension,
  getOfficePreviewRoute,
} from '@/lib/mimeForPreview';
import {
  OfficeOoxmlPreview,
  type OfficeOoxmlPreviewRoute,
} from '@/components/files/OfficeOoxmlPreview';
import { parseCsvForPreview } from '@/lib/parseCsvForPreview';
import { CodeBlock } from '@/components/chat/markdown/CodeBlock';
import { Markdown } from '@/components/chat/markdown/Markdown';
import { useFilePreviewActions } from '@/components/files/useFilePreviewActions';

/** `fill`: parent supplies height (e.g. Knowledge sidebar); inner area scrolls. */
export type UniversalFilePreviewLayout = 'default' | 'fill';

interface UniversalFilePreviewProps {
  fileId: string;
  fileName: string;
  mimeType?: string | null;
  sizeBytes?: number;
  className?: string;
  showActions?: boolean;
  /** When false, Open/Download are not rendered (e.g. shown in `ArtifactHeader` instead). */
  showToolbar?: boolean;
  /** Use `fill` when embedded in a flex column with bounded height so preview scrolls inside the panel. */
  layout?: UniversalFilePreviewLayout;
}

const TEXT_PREVIEW_LIMIT = 2 * 1024 * 1024;

/** Capped height when parent does not constrain (avoids `100%` resolving to content height). */
const SCROLL_MAX_DEFAULT = 'max-h-[min(65vh,28rem)]';

function formatJsonForDisplay(raw: string): { ok: true; text: string } | { ok: false } {
  const trimmed = raw.trim();
  if (!trimmed) return { ok: true, text: '' };
  try {
    const parsed = JSON.parse(trimmed);
    return { ok: true, text: JSON.stringify(parsed, null, 2) };
  } catch {
    return { ok: false };
  }
}

/** Preview is loaded via fetch + blob so Authorization Bearer is sent (plain &lt;img src&gt; cannot). */
function binaryPreviewKind(mime: string): 'image' | 'pdf' | 'audio' | 'video' | null {
  if (mime.startsWith('image/')) return 'image';
  if (mime === 'application/pdf') return 'pdf';
  if (mime.startsWith('audio/')) return 'audio';
  if (mime.startsWith('video/')) return 'video';
  return null;
}

export function UniversalFilePreview({
  fileId,
  fileName,
  mimeType,
  sizeBytes = 0,
  className,
  showActions = true,
  showToolbar = true,
  layout = 'default',
}: UniversalFilePreviewProps) {
  const { t } = useTranslation();
  const fill = layout === 'fill';
  const effectiveMime = useMemo(
    () => resolveEffectiveMime(mimeType, fileName),
    [mimeType, fileName],
  );

  const officeRoute = useMemo(
    () => getOfficePreviewRoute(fileName, effectiveMime),
    [fileName, effectiveMime],
  );
  const isOoxmlPreviewable =
    officeRoute === 'docx' ||
    officeRoute === 'xlsx' ||
    officeRoute === 'pptx';

  const { previewUrl, downloadBusy, openBusy, handleDownloadClick, handleOpenClick } =
    useFilePreviewActions(fileId, fileName);

  const [textContent, setTextContent] = useState<string>('');
  const [textLoading, setTextLoading] = useState(false);
  const [textFailed, setTextFailed] = useState(false);
  const [textIsBinary, setTextIsBinary] = useState(false);

  const objectUrlRef = useRef<string | null>(null);
  const [binarySrc, setBinarySrc] = useState<string | null>(null);
  const [binaryLoading, setBinaryLoading] = useState(false);
  const [binaryError, setBinaryError] = useState(false);
  const [readerOpen, setReaderOpen] = useState(false);
  // The artifact panel (showToolbar=false) manages its own reader/header, so
  // skip the inline affordance there to avoid a redundant trigger + chrome.
  const showReaderAffordance = showToolbar;

  const officeByName = hasOfficePreviewExtension(fileName);
  const isOfficeBlockingText =
    (isOfficeDocumentMime(effectiveMime) || officeByName) &&
    !isOoxmlPreviewable;

  const showOfficeUnsupported =
    (officeByName || isOfficeDocumentMime(effectiveMime)) &&
    !isOoxmlPreviewable;

  const canTextPreview =
    !isOfficeBlockingText &&
    isTextLikeMime(effectiveMime) &&
    sizeBytes <= TEXT_PREVIEW_LIMIT;

  const isJson = isJsonPreviewMime(effectiveMime);
  const isMarkdown = isMarkdownPreviewMime(effectiveMime);
  const isCsv = isCsvPreviewMime(effectiveMime, fileName);
  const binaryKind = binaryPreviewKind(effectiveMime);

  useEffect(() => {
    if (!canTextPreview) return;
    let cancelled = false;
    const token = getAccessToken();
    setTextLoading(true);
    setTextFailed(false);
    setTextIsBinary(false);

    fetch(previewUrl, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      credentials: 'include',
    })
      .then(async (res) => {
        if (!res.ok) throw new Error('Preview request failed');
        return res.text();
      })
      .then((value) => {
        if (cancelled) return;
        if (looksLikeBinaryString(value)) {
          setTextIsBinary(true);
          setTextContent('');
          return;
        }
        setTextContent(value);
      })
      .catch(() => {
        if (!cancelled) setTextFailed(true);
      })
      .finally(() => {
        if (!cancelled) setTextLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [canTextPreview, previewUrl]);

  useEffect(() => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setBinarySrc(null);
    setBinaryError(false);

    if (!binaryKind) {
      setBinaryLoading(false);
      return;
    }

    let cancelled = false;
    const token = getAccessToken();
    setBinaryLoading(true);

    fetch(previewUrl, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      credentials: 'include',
    })
      .then(async (res) => {
        if (!res.ok) throw new Error('Preview request failed');
        const headerType = res.headers
          .get('Content-Type')
          ?.split(';')[0]
          ?.trim()
          .toLowerCase();
        const buf = await res.arrayBuffer();
        const useType =
          headerType && headerType !== 'application/octet-stream'
            ? headerType
            : effectiveMime;
        return URL.createObjectURL(new Blob([buf], { type: useType }));
      })
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrlRef.current = url;
        setBinarySrc(url);
        setBinaryError(false);
      })
      .catch(() => {
        if (!cancelled) setBinaryError(true);
      })
      .finally(() => {
        if (!cancelled) setBinaryLoading(false);
      });

    return () => {
      cancelled = true;
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [previewUrl, effectiveMime, binaryKind]);

  const jsonBody = useMemo(() => {
    if (!isJson || !textContent) return null;
    if (effectiveMime === 'application/jsonl') {
      return (
        <CodeBlock language="jsonl">
          <code className="font-mono">{textContent}</code>
        </CodeBlock>
      );
    }
    const fmt = formatJsonForDisplay(textContent);
    const display = fmt.ok ? fmt.text : textContent;
    return (
      <CodeBlock language="json">
        <code className="font-mono">{display}</code>
      </CodeBlock>
    );
  }, [isJson, textContent, effectiveMime]);

  const csvTable = useMemo(() => {
    if (!isCsv || !textContent) return null;
    const parsed = parseCsvForPreview(textContent);
    if (parsed.rows.length === 0) return null;
    const width = Math.min(
      64,
      Math.max(1, ...parsed.rows.map((r) => r.length)),
    );
    const rows = parsed.rows.map((r) => {
      const next = r.slice(0, width);
      while (next.length < width) next.push('');
      return next;
    });
    return { ...parsed, rows };
  }, [isCsv, textContent]);

  const mediaScrollWrap = (child: ReactNode) => (
    <div
      className={cn(
        'flex min-h-0 w-full justify-center overflow-auto',
        fill
          ? 'flex-1 flex-col items-center py-2'
          : cn(SCROLL_MAX_DEFAULT, 'min-h-[12rem] items-start'),
      )}
    >
      {child}
    </div>
  );

  let body: ReactNode;
  if (isOoxmlPreviewable && officeRoute) {
    body = (
      <OfficeOoxmlPreview
        previewUrl={previewUrl}
        route={officeRoute as OfficeOoxmlPreviewRoute}
        fileName={fileName}
        layout={layout}
      />
    );
  } else if (showOfficeUnsupported) {
    body = (
      <div
        className={cn(
          'rounded-lg border border-border bg-surface-sunken p-5 text-center',
          fill && 'flex min-h-0 flex-1 flex-col justify-center',
        )}
      >
        <FileText className="w-8 h-8 mx-auto mb-2 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          {officeRoute === 'openDocument'
            ? t('common.filePreview.openDocument')
            : t('common.filePreview.officeLegacy')}
        </p>
      </div>
    );
  } else if (binaryKind === 'image') {
    body = mediaScrollWrap(
      binaryLoading ? (
        <p className="text-sm text-muted-foreground py-8">Loading image…</p>
      ) : binaryError ? (
        <p className="text-sm text-muted-foreground text-center py-8 px-2">
          Could not load the image preview (sign in may be required). Try Download
          below.
        </p>
      ) : binarySrc ? (
        <img
          src={binarySrc}
          alt={fileName}
          className={cn(
            'max-w-full w-auto h-auto object-contain rounded-lg',
            fill ? 'max-h-[min(75dvh,900px)]' : 'max-h-[min(60vh,28rem)]',
          )}
        />
      ) : null,
    );
  } else if (binaryKind === 'pdf') {
    body = binaryLoading ? (
      <div
        className={cn(
          'flex w-full items-center justify-center py-8',
          fill && 'min-h-0 flex-1',
        )}
      >
        <p className="text-sm text-muted-foreground">Loading PDF…</p>
      </div>
    ) : binaryError ? (
      <div
        className={cn(
          'rounded-lg border border-border bg-surface-sunken p-5 text-center',
          fill && 'flex min-h-0 flex-1 flex-col justify-center',
        )}
      >
        <p className="text-sm text-muted-foreground">
          Could not load the PDF preview. Try opening the download link instead.
        </p>
      </div>
    ) : binarySrc ? (
      readerOpen && showReaderAffordance ? (
        <div
          className={cn(
            'flex w-full flex-col',
            fill ? 'min-h-0 flex-1' : 'min-h-[60vh] h-[70vh]',
          )}
        >
          <Suspense
            fallback={
              <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-muted-foreground">
                {t('pdfReader.loading', { defaultValue: 'Loading PDF…' })}
              </div>
            }
          >
            <PdfReader
              target={{ fileId, fileName, mimeType: effectiveMime, sizeBytes }}
              initialMode="research"
              onClose={() => setReaderOpen(false)}
            />
          </Suspense>
        </div>
      ) : (
        <div
          className={cn(
            'flex w-full flex-col gap-2',
            fill ? 'min-h-0 flex-1' : '',
          )}
        >
          {showReaderAffordance && (
            <div className="flex flex-shrink-0 items-center gap-2">
              <Button
                type="button"
                onClick={() => setReaderOpen(true)}
                leftIcon={<GraduationCap className="h-4 w-4" />}
              >
                {t('pdfReader.researchMode', { defaultValue: 'Research Mode' })}
              </Button>
            </div>
          )}
          <iframe
            src={binarySrc}
            title={fileName}
            className={cn(
              'w-full rounded-lg border border-border',
              fill
                ? 'min-h-0 flex-1'
                : 'min-h-[50vh] max-h-[min(70vh,28rem)]',
            )}
          />
        </div>
      )
    ) : null;
  } else if (binaryKind === 'audio') {
    body = binaryLoading ? (
      <p className="text-sm text-muted-foreground">Loading audio…</p>
    ) : binaryError ? (
      <p className="text-sm text-muted-foreground">Audio preview failed.</p>
    ) : binarySrc ? (
      <audio src={binarySrc} controls className="w-full" />
    ) : null;
  } else if (binaryKind === 'video') {
    body = mediaScrollWrap(
      binaryLoading ? (
        <p className="text-sm text-muted-foreground py-8">Loading video…</p>
      ) : binaryError ? (
        <p className="text-sm text-muted-foreground text-center py-8">
          Video preview failed.
        </p>
      ) : binarySrc ? (
        <video
          src={binarySrc}
          controls
          className={cn(
            'w-full rounded-lg',
            fill ? 'max-h-[min(75dvh,900px)]' : 'max-h-[min(70vh,28rem)]',
          )}
        />
      ) : null,
    );
  } else if (canTextPreview) {
    body = (
      <div
        className={cn(
          'rounded-lg border border-border bg-surface-sunken p-3',
          fill
            ? 'flex min-h-0 w-full flex-1 flex-col overflow-y-auto overscroll-y-contain'
            : cn(
                SCROLL_MAX_DEFAULT,
                'min-h-0 overflow-y-auto overscroll-y-contain',
              ),
        )}
      >
        {textLoading ? (
          <p className="text-sm text-muted-foreground">Loading preview...</p>
        ) : textFailed ? (
          <p className="text-sm text-muted-foreground">
            Preview unavailable for this file. You can still download it.
          </p>
        ) : textIsBinary ? (
          <p className="text-sm text-muted-foreground text-center py-6">
            This file looks like a binary or compressed document (for example Office
            or archive). Inline text preview is not shown.
            {showActions
              ? ' Use Open or Download instead.'
              : ' Use Download instead.'}
          </p>
        ) : isMarkdown ? (
          <Markdown
            content={textContent}
            className="prose prose-sm dark:prose-invert max-w-none text-foreground px-1"
          />
        ) : isJson ? (
          jsonBody
        ) : isCsv && csvTable && csvTable.rows.length > 0 ? (
          <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
            {(csvTable.truncatedRows ||
              csvTable.truncatedScan ||
              csvTable.truncatedCols) && (
              <p className="flex-shrink-0 text-[11px] text-muted-foreground leading-snug">
                {csvTable.truncatedRows
                  ? `Showing the first ${csvTable.rows.length} rows. `
                  : null}
                {csvTable.truncatedScan
                  ? 'Preview is truncated from a very large file. '
                  : null}
                {csvTable.truncatedCols
                  ? `Showing the first ${csvTable.rows[0]?.length ?? 0} columns. `
                  : null}
              </p>
            )}
            <div className="min-h-0 flex-1 overflow-auto rounded-md border border-border-subtle">
              <table className="w-max min-w-full border-collapse text-left text-[11px] text-foreground">
                <thead>
                  <tr>
                    {(csvTable.rows[0] ?? []).map((cell, colIdx) => (
                      <th
                        key={colIdx}
                        scope="col"
                        className="sticky top-0 z-[1] max-w-[min(18rem,45vw)] border-b border-border-subtle bg-surface-sunken px-2 py-1.5 align-top font-medium leading-snug text-foreground"
                      >
                        <span className="block break-words whitespace-normal">
                          {cell || '\u00a0'}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {csvTable.rows.slice(1).map((dataRow, rowIdx) => {
                    const header = csvTable.rows[0] ?? [];
                    return (
                      <tr
                        key={rowIdx}
                        className="even:bg-surface-sunken/35 border-b border-border-subtle/60 last:border-b-0"
                      >
                        {header.map((_, colIdx) => (
                          <td
                            key={colIdx}
                            className="max-w-[min(18rem,45vw)] px-2 py-1.5 align-top leading-snug"
                          >
                            <span className="block break-words whitespace-normal text-foreground">
                              {(dataRow[colIdx] ?? '') || '\u00a0'}
                            </span>
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <pre className="text-xs text-foreground whitespace-pre-wrap break-words font-mono">
            {textContent}
          </pre>
        )}
      </div>
    );
  } else {
    body = (
      <div
        className={cn(
          'rounded-lg border border-border bg-surface-sunken p-5 text-center',
          fill && 'flex min-h-0 flex-1 flex-col justify-center',
        )}
      >
        <FileText className="w-8 h-8 mx-auto mb-2 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          {t('common.filePreview.unavailable')}
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'flex min-h-0 w-full flex-col',
        fill ? 'h-full min-h-0 flex-1' : 'h-full',
        className,
      )}
    >
      {showActions && showToolbar && (
        <div className="mb-3 flex flex-shrink-0 items-center gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={openBusy}
            onClick={handleOpenClick}
            leftIcon={<ExternalLink className="w-4 h-4" />}
          >
            {t('common.open')}
          </Button>
          <Button
            type="button"
            disabled={downloadBusy}
            onClick={handleDownloadClick}
            leftIcon={<Download className="w-4 h-4" />}
          >
            {t('knowledge.download')}
          </Button>
        </div>
      )}
      <div
        className={cn(
          'min-h-0 w-full flex flex-col',
          fill
            ? 'flex flex-1 flex-col overflow-hidden'
            : 'flex-1 overflow-hidden',
        )}
      >
        {body}
      </div>
    </div>
  );
}
