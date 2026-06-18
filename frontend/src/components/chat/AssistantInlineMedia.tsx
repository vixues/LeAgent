import { useTranslation } from 'react-i18next';
import type { Attachment } from '@/types/chat';
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

/**
 * Renders assistant-produced media (image / video / audio) inline within the
 * message body, ChatGPT-style. Unrenderable kinds fall back to a download card.
 */
export function AssistantInlineMedia({ media, native }: AssistantInlineMediaProps) {
  const { t } = useTranslation();
  if (!Array.isArray(media) || media.length === 0) return null;

  return (
    <div className="mt-3 space-y-3" data-native-media={native ? 'true' : 'false'}>
      {media.map((att) => {
        const src = mediaSrc(att);
        if (isImage(att)) {
          return (
            <ChatImage
              key={att.id}
              src={src}
              alt={att.name || t('chat.assistantMedia.imageAlt', 'Generated image')}
              className="max-w-full rounded-xl"
            />
          );
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
