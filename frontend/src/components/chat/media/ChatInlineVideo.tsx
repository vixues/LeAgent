import { cn } from '@/lib/utils';

/** Inline responsive video for Markdown links to ``.mp4`` / ``.webm`` etc. */
export function ChatInlineVideo({ src, title }: { src: string; title?: string }) {
  return (
    <div
      className={cn(
        'my-3 overflow-hidden rounded-xl border border-border-subtle bg-black/80 shadow-soft',
        'max-w-full',
      )}
    >
      <video
        src={src}
        controls
        playsInline
        preload="metadata"
        className="max-h-[min(70vh,480px)] w-full object-contain"
        aria-label={title ?? 'Video'}
      />
    </div>
  );
}
