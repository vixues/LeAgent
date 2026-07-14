import type { MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Download } from 'lucide-react';
import type { Attachment } from '@/types/chat';
import {
  extractApiFileDownloadId,
  extractApiFilePreviewId,
} from './media/chatMediaUtils';
import { downloadAuthenticatedFile } from '@/lib/downloadAuthenticatedFile';
import { ChatImage } from './media/ChatImage';
import { ChatInlineVideo } from './media/ChatInlineVideo';
import { ChatInlineModel3D } from './media/ChatInlineModel3D';
import { AttachmentCard } from './AttachmentCard';

interface AssistantInlineMediaProps {
  media: Attachment[];
  /** True when produced by a model with native image output (vs. tool output). */
  native?: boolean;
}

function mediaSrc(att: Attachment): string {
  return att.previewUrl || att.downloadUrl || att.url || '';
}

function isImage(att: Attachment): boolean {
  return att.kind === 'image' || att.type?.startsWith('image/');
}

function isVideo(att: Attachment): boolean {
  return att.kind === 'video' || att.type?.startsWith('video/');
}

function isAudio(att: Attachment): boolean {
  return att.kind === 'audio' || att.type?.startsWith('audio/');
}

function isModel3D(att: Attachment): boolean {
  return (
    att.kind === 'model3d' ||
    att.type === 'model/gltf-binary' ||
    /\.(glb|gltf)$/i.test(att.name || '')
  );
}

function AssistantInlineImage({ attachment }: { attachment: Attachment }) {
  const { t } = useTranslation();
  const src = mediaSrc(attachment);
  const downloadTarget = attachment.downloadUrl || src;
  const managedId =
    extractApiFileDownloadId(downloadTarget) ??
    extractApiFilePreviewId(attachment.previewUrl);
  const downloadLabel = t('chat.attachments.download', {
    defaultValue: 'Download {{name}}',
    name: attachment.name,
  });

  const handleDownload = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    if (managedId) {
      void downloadAuthenticatedFile(managedId, attachment.name);
    }
  };

  return (
    <div className="max-w-full overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-soft">
      <ChatImage
        src={src}
        alt={attachment.name || t('chat.assistantMedia.imageAlt', 'Generated image')}
        className="max-w-full rounded-none"
      />
      <div className="flex items-center justify-between gap-2 border-t border-border-subtle px-2.5 py-2">
        <span className="min-w-0 truncate text-xs text-muted-foreground">
          {attachment.name}
        </span>
        {managedId ? (
          <button
            type="button"
            onClick={handleDownload}
            className="shrink-0 rounded-md p-1 text-muted-foreground-tertiary transition-colors hover:bg-surface-sunken hover:text-foreground"
            aria-label={downloadLabel}
            title={downloadLabel}
          >
            <Download className="h-3.5 w-3.5" />
          </button>
        ) : downloadTarget ? (
          <a
            href={downloadTarget}
            download={attachment.name}
            className="shrink-0 rounded-md p-1 text-muted-foreground-tertiary transition-colors hover:bg-surface-sunken hover:text-foreground"
            aria-label={downloadLabel}
            title={downloadLabel}
          >
            <Download className="h-3.5 w-3.5" />
          </a>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Renders assistant-produced media (image / video / audio) inline within the
 * message body, ChatGPT-style. Unrenderable kinds fall back to a download card.
 */
export function AssistantInlineMedia({ media, native }: AssistantInlineMediaProps) {
  if (!Array.isArray(media) || media.length === 0) return null;

  return (
    <div className="mt-3 space-y-3" data-native-media={native ? 'true' : 'false'}>
      {media.map((att) => {
        const src = mediaSrc(att);
        if (isImage(att)) {
          return <AssistantInlineImage key={att.id} attachment={att} />;
        }
        if (isVideo(att)) {
          return <ChatInlineVideo key={att.id} src={src} title={att.name} />;
        }
        if (isModel3D(att)) {
          return <ChatInlineModel3D key={att.id} src={src} title={att.name} />;
        }
        if (isAudio(att)) {
          return (
            <audio key={att.id} src={src} controls className="w-full" aria-label={att.name} />
          );
        }
        return <AttachmentCard key={att.id} attachment={att} />;
      })}
    </div>
  );
}
