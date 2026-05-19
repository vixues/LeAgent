import { useMemo, useState, type MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Download,
  FileArchive,
  FileAudio,
  FileCode,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
  File as FileIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Attachment } from '@/types/chat';
import { ChatImage } from '@/components/chat/media/ChatImage';
import { extractApiFileDownloadId, extractApiFilePreviewId, isInvalidApiFilePreviewRef, managedFilePreviewHasSignedToken } from '@/components/chat/media/chatMediaUtils';
import { useChatFileBlobUrl } from '@/hooks/useChatFileBlobUrl';
import { downloadAuthenticatedFile } from '@/lib/downloadAuthenticatedFile';

interface AttachmentCardProps {
  attachment: Attachment;
  className?: string;
}

/**
 * Inline card shown on the user turn for each file attached to a message.
 *
 * Built to match the data shape the backend `SessionManager.attach_files`
 * hands the frontend via the SSE `attachments` event:
 *
 *   { id, filename, kind, content_type, size, preview_url, download_url }
 *
 * Images with a `preview_url` render a 56×56 thumbnail. Everything else
 * renders as a chip with a kind-aware lucide icon. Both variants expose a
 * download affordance that consumes the short-lived signed URL so clicks
 * cannot leak into long-lived links in exported conversations.
 */
export function AttachmentCard({ attachment, className }: AttachmentCardProps) {
  const [previewFailed, setPreviewFailed] = useState(false);

  const kind = useMemo(() => deriveKind(attachment), [attachment]);
  const sizeLabel = useMemo(() => formatSize(attachment.size), [attachment.size]);

  const previewSource = attachment.previewUrl ?? attachment.url ?? attachment.downloadUrl;
  const openTarget = previewSource ?? attachment.downloadUrl;
  const downloadTarget = attachment.downloadUrl ?? previewSource;
  const previewFileId = extractApiFilePreviewId(previewSource);
  const invalidPreviewRef = isInvalidApiFilePreviewRef(previewSource);
  const videoManagedId = invalidPreviewRef ? null : previewFileId;
  const { blobUrl: videoBlobUrl } = useChatFileBlobUrl(videoManagedId);
  const downloadFileId = extractApiFileDownloadId(downloadTarget);
  const isImageAttachment =
    kind === 'image' ||
    attachment.type?.toLowerCase().startsWith('image/') ||
    hasImageExtension(attachment.name);
  const isVideoAttachment =
    kind === 'video' ||
    attachment.type?.toLowerCase().startsWith('video/') ||
    hasVideoExtension(attachment.name);
  const showImagePreview = isImageAttachment && !!previewSource && !previewFailed;
  const showVideoPreview = isVideoAttachment && !!previewSource && !previewFailed;

  const handleDownload = (event: MouseEvent<HTMLButtonElement | HTMLAnchorElement>) => {
    if (!downloadFileId) return;
    event.preventDefault();
    void downloadAuthenticatedFile(downloadFileId, attachment.name);
  };

  if (showImagePreview) {
    return (
      <div
        className={cn(
          'self-start max-w-xs min-w-0 overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-soft',
          className,
        )}
        title={`${attachment.name} · ${sizeLabel}`}
      >
        <ChatImage src={previewSource} alt={attachment.name} />
        <div className="flex items-center justify-between gap-2 border-t border-border-subtle px-2 py-1.5">
          <span className="min-w-0 truncate text-xs text-muted-foreground">{attachment.name}</span>
          {downloadTarget ? (
            <AttachmentDownloadButton
              href={downloadTarget}
              filename={attachment.name}
              onAuthenticatedDownload={downloadFileId ? handleDownload : undefined}
              className="flex-shrink-0 rounded-md p-1 text-muted-foreground-tertiary hover:bg-surface-sunken hover:text-foreground"
            />
          ) : null}
        </div>
      </div>
    );
  }

  if (showVideoPreview) {
    return (
      <div
        className={cn(
          'self-start max-w-md min-w-0 overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-soft',
          className,
        )}
        title={`${attachment.name} · ${sizeLabel}`}
      >
        <video
          src={
            videoManagedId
              ? videoBlobUrl ??
                (managedFilePreviewHasSignedToken(previewSource ?? '') ? previewSource : undefined)
              : previewSource
          }
          controls
          playsInline
          preload="metadata"
          className="max-h-56 w-full bg-black/80 object-contain"
          aria-label={attachment.name}
          onError={() => setPreviewFailed(true)}
        />
        <div className="flex items-center justify-between gap-2 border-t border-border-subtle px-2 py-1.5">
          <span className="min-w-0 truncate text-xs text-muted-foreground">{attachment.name}</span>
          {downloadTarget ? (
            <AttachmentDownloadButton
              href={downloadTarget}
              filename={attachment.name}
              onAuthenticatedDownload={downloadFileId ? handleDownload : undefined}
              className="flex-shrink-0 rounded-md p-1 text-muted-foreground-tertiary hover:bg-surface-sunken hover:text-foreground"
            />
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'inline-flex self-start items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs',
        'bg-surface border border-border-subtle',
        'text-muted-foreground hover:bg-surface-sunken transition-colors',
        className,
      )}
      title={`${attachment.name} · ${sizeLabel}`}
    >
      <KindIcon kind={kind} />
      <div className="flex flex-col min-w-0">
        <a
          href={openTarget ?? '#'}
          target="_blank"
          rel="noopener noreferrer"
          className={cn(
            'max-w-[180px] truncate font-medium',
            openTarget ? 'hover:underline' : 'pointer-events-none',
          )}
        >
          {attachment.name}
        </a>
        <span className="text-muted-foreground-tertiary tabular-nums text-[11px]">
          {sizeLabel}
        </span>
      </div>
      {downloadTarget && (
        <AttachmentDownloadButton
          href={downloadTarget}
          filename={attachment.name}
          onAuthenticatedDownload={downloadFileId ? handleDownload : undefined}
          className="ml-1 p-1 rounded-md text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors"
        />
      )}
    </div>
  );
}

function AttachmentDownloadButton({
  href,
  filename,
  onAuthenticatedDownload,
  className,
}: {
  href: string;
  filename: string;
  onAuthenticatedDownload?: (event: MouseEvent<HTMLButtonElement | HTMLAnchorElement>) => void;
  className?: string;
}) {
  const { t } = useTranslation();
  const label = t('chat.attachments.download', {
    defaultValue: 'Download {{name}}',
    name: filename,
  });
  const content = <Download className="w-3.5 h-3.5" />;
  if (onAuthenticatedDownload) {
    return (
      <button
        type="button"
        onClick={onAuthenticatedDownload}
        className={className}
        aria-label={label}
        title={label}
      >
        {content}
      </button>
    );
  }
  return (
    <a
      href={href}
      download={filename}
      className={className}
      aria-label={label}
      title={label}
    >
      {content}
    </a>
  );
}

function deriveKind(att: Attachment): string {
  if (att.kind) return att.kind;
  const ct = att.type?.toLowerCase() ?? '';
  if (ct.startsWith('image/')) return 'image';
  if (ct.startsWith('audio/')) return 'audio';
  if (ct.startsWith('video/')) return 'video';
  if (ct.includes('zip') || ct.includes('tar') || ct.includes('gzip'))
    return 'archive';
  if (ct.includes('pdf') || ct.includes('msword') || ct.includes('wordprocessing'))
    return 'document';
  if (ct.includes('spreadsheet') || ct.includes('excel') || ct.includes('csv'))
    return 'data';
  if (
    ct.includes('json') ||
    ct.includes('xml') ||
    ct.includes('yaml') ||
    ct.includes('javascript') ||
    ct.includes('typescript') ||
    ct.includes('python')
  )
    return 'code';
  if (ct.startsWith('text/')) return 'document';
  return 'other';
}

function KindIcon({ kind }: { kind: string }) {
  const cls = 'w-3.5 h-3.5 flex-shrink-0';
  switch (kind) {
    case 'image':
      return <FileImage className={cls} />;
    case 'audio':
      return <FileAudio className={cls} />;
    case 'video':
      return <FileVideo className={cls} />;
    case 'archive':
      return <FileArchive className={cls} />;
    case 'document':
      return <FileText className={cls} />;
    case 'data':
      return <FileSpreadsheet className={cls} />;
    case 'code':
      return <FileCode className={cls} />;
    default:
      return <FileIcon className={cls} />;
  }
}

function formatSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function hasImageExtension(filename: string) {
  const match = filename.toLowerCase().match(/\.([a-z0-9]+)$/);
  if (!match) return false;
  const ext = match[1];
  return (
    ext === 'png' ||
    ext === 'jpg' ||
    ext === 'jpeg' ||
    ext === 'gif' ||
    ext === 'webp' ||
    ext === 'bmp' ||
    ext === 'svg' ||
    ext === 'avif' ||
    ext === 'heic' ||
    ext === 'heif'
  );
}

function hasVideoExtension(filename: string) {
  const match = filename.toLowerCase().match(/\.([a-z0-9]+)$/);
  if (!match) return false;
  const ext = match[1];
  return (
    ext === 'mp4' ||
    ext === 'webm' ||
    ext === 'mov' ||
    ext === 'm4v' ||
    ext === 'ogg'
  );
}
