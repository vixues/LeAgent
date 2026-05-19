import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { useChatDraftStore } from '@/stores/chatDraft';
import { Button } from '@/components/ui/Button';

interface CameraCaptureModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CameraCaptureModal({ open, onOpenChange }: CameraCaptureModalProps) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const setComposerFiles = useChatDraftStore((s) => s.setComposerFiles);
  const [error, setError] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);

  useEffect(() => {
    if (!open) {
      streamRef.current?.getTracks().forEach((tr) => tr.stop());
      streamRef.current = null;
      setError(null);
      setCapturing(false);
      return;
    }

    let cancelled = false;
    setError(null);

    void (async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) {
          setError(
            t('chat.camera.notSupported', {
              defaultValue: 'Camera is not supported in this browser.',
            }),
          );
          return;
        }
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'user' }, width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((tr) => tr.stop());
          return;
        }
        streamRef.current = stream;
        const v = videoRef.current;
        if (v) {
          v.srcObject = stream;
          await v.play().catch(() => {});
        }
      } catch {
        setError(
          t('chat.camera.permissionDenied', {
            defaultValue: 'Could not access the camera. Check permissions.',
          }),
        );
      }
    })();

    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((tr) => tr.stop());
      streamRef.current = null;
    };
  }, [open, t]);

  const handleCapture = useCallback(() => {
    const video = videoRef.current;
    if (!video || error || capturing) return;
    const w = video.videoWidth;
    const h = video.videoHeight;
    if (!w || !h) return;

    setCapturing(true);
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      setCapturing(false);
      return;
    }
    ctx.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          setCapturing(false);
          return;
        }
        const file = new File([blob], `camera-${Date.now()}.jpg`, {
          type: 'image/jpeg',
        });
        setComposerFiles((prev) => [...prev, file]);
        streamRef.current?.getTracks().forEach((tr) => tr.stop());
        streamRef.current = null;
        onOpenChange(false);
        setCapturing(false);
      },
      'image/jpeg',
      0.92,
    );
  }, [capturing, error, onOpenChange, setComposerFiles]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md" className="gap-0 p-0 overflow-hidden">
        <DialogHeader className="px-4 pt-4 pb-2 border-b border-border-subtle">
          <DialogTitle className="text-base">
            {t('chat.camera.title', { defaultValue: 'Take a photo' })}
          </DialogTitle>
        </DialogHeader>
        <div className="px-4 py-3">
          {error ? (
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          ) : (
            <video
              ref={videoRef}
              playsInline
              muted
              autoPlay
              className="w-full max-h-[min(50vh,320px)] rounded-lg bg-black object-cover"
            />
          )}
        </div>
        <DialogFooter className="rounded-b-xl border-t border-border-subtle">
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="rounded-lg border border-border-subtle px-3 py-1.5 text-sm text-muted-foreground hover:bg-surface-sunken hover:text-foreground transition-colors"
          >
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </button>
          <Button
            type="button"
            size="sm"
            variant="primary"
            disabled={Boolean(error) || capturing}
            onClick={() => void handleCapture()}
          >
            {t('chat.camera.capture', { defaultValue: 'Add to message' })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
