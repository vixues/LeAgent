import {
  Dialog,
  DialogContent,
  DialogClose,
} from '@/components/ui/Dialog';
import { cn } from '@/lib/utils';

interface MediaLightboxProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  src: string;
  alt: string;
  kind?: 'image' | 'video';
}

export function MediaLightbox({
  open,
  onOpenChange,
  src,
  alt,
  kind = 'image',
}: MediaLightboxProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        size="xl"
        className={cn('max-w-[min(96vw,56rem)] border-border-subtle bg-surface p-0')}
      >
        <div className="relative flex max-h-[85vh] items-center justify-center p-2">
          <DialogClose
            className="absolute right-2 top-2 z-[1] rounded-lg border border-border-subtle bg-surface/90 p-1.5 text-muted-foreground shadow-soft hover:bg-surface-sunken hover:text-foreground"
            aria-label="Close"
          />
          {kind === 'video' ? (
            <video
              src={src}
              controls
              playsInline
              className="max-h-[80vh] max-w-full rounded-lg"
              aria-label={alt}
            >
              <track kind="captions" />
            </video>
          ) : (
            <img
              src={src}
              alt={alt}
              className="max-h-[80vh] max-w-full rounded-lg object-contain"
            />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
